import math

import numpy as np
import torch
from torch.distributions import kl_divergence
from torch.nn import Module

from .prob_utils import normal_parse_params


class VAEAC(Module):
    """Variational Autoencoder with Arbitrary Conditioning core model.

    It is rather flexible, but has several assumptions:
    - The batch of objects and the mask of unobserved features have the same shape.
    - The prior and proposal distributions in the latent space are component-wise
      independent Gaussians.

    Parameters
    ----------
    prior_network : callable
        Network that takes as input the concatenation of the batch of objects and
        the mask of unobserved features, and returns the parameters of Gaussians
        in the latent space for the prior distribution. The output range should
        not be restricted.
    proposal_network : callable
        Network that takes as input the concatenation of the batch of objects and
        the mask of unobserved features, and returns the parameters of Gaussians
        in the latent space for the proposal distribution. The output range should
        not be restricted.
    generative_network : callable
        Network that takes latent representation as input and returns the parameters
        of generative distribution p_theta(x_b | z, x_{1 - b}, b), where b is the mask
        of unobserved features. The information about x_{1 - b} and b can be transmitted
        to generative network from prior network through nn_utils.MemoryLayer. It is
        guaranteed that for every batch, prior network is always executed before
        generative network.
    rec_log_prob : callable
        Reconstruction log probability function that takes (groundtruth, distr_params, mask)
        as input and returns a vector of differentiable log probabilities
        p_theta(x_b | z, x_{1 - b}, b) for each object in the batch.
    sigma_mu : float, optional
        Coefficient of the regularization in the hidden space for the mean.
        Default corresponds to very weak regularization.
    sigma_sigma : float, optional
        Coefficient of the regularization in the hidden space for the standard deviation.
        Default corresponds to very weak regularization.

    Notes
    -----
    The default values for sigma_mu and sigma_sigma correspond to a very weak,
    almost disappearing regularization, which is suitable for all experimental
    setups the model was tested on.
    """
    def __init__(self, rec_log_prob, proposal_network, prior_network,
                 generative_network, sampler_network, one_hot_max_sizes, sigma_mu=1e4, sigma_sigma=1e-4):
        super().__init__()
        self.rec_log_prob = rec_log_prob
        self.proposal_network = proposal_network
        self.prior_network = prior_network
        self.generative_network = generative_network
        self.sampler_network = sampler_network
        self.one_hot_max_sizes = one_hot_max_sizes
        self.sigma_mu = sigma_mu
        self.sigma_sigma = sigma_sigma

    def make_observed(self, batch, mask):
        """
        Copy batch of objects and zero unobserved features.
        """
        observed = batch.detach().clone()
        observed[mask.bool()] = 0
        return observed

    def make_latent_distributions(self, batch, mask, no_proposal=False):
        """
        Make latent distributions for the given batch and mask.
        No no_proposal is True, return None instead of proposal distribution.
        """
        observed = self.make_observed(batch, mask)
        if no_proposal:
            proposal = None
        else:
            full_info = torch.cat([batch, mask], 1)
            proposal_params = self.proposal_network(full_info)
            proposal = normal_parse_params(proposal_params, 1e-3)
        prior_params = self.prior_network(torch.cat([observed, mask], 1))
        prior = normal_parse_params(prior_params, 1e-3)
        return proposal, prior

    def prior_regularization(self, prior):
        """
        The prior distribution regularization in the latent space.
        Though it saves prior distribution parameters from going to infinity,
        the model usually doesn't diverge even without this regularization.
        It almost doesn't affect learning process near zero with default
        regularization parameters which are recommended to be used.
        """
        num_objects = prior.mean.shape[0]
        mu = prior.mean.view(num_objects, -1)
        sigma = prior.scale.view(num_objects, -1)
        mu_regularizer = -(mu ** 2).sum(-1) / 2 / (self.sigma_mu ** 2)
        sigma_regularizer = (sigma.log() - sigma).sum(-1) * self.sigma_sigma
        return mu_regularizer + sigma_regularizer

    def batch_vlb(self, batch, mask):
        """
        Compute differentiable lower bound for the given batch of objects
        and mask.
        """
        proposal, prior = self.make_latent_distributions(batch, mask)
        prior_regularization = self.prior_regularization(prior)
        latent = proposal.rsample()
        rec_params = self.generative_network(latent)
        rec_loss = self.rec_log_prob(batch, rec_params, mask)
        kl = kl_divergence(proposal, prior).view(batch.shape[0], -1).sum(-1)
        return rec_loss - kl + prior_regularization

    def batch_iwae(self, batch, mask, K):
        """
        Compute IWAE log likelihood estimate with K samples per object.
        Technically, it is differentiable, but it is recommended to use it
        for evaluation purposes inside torch.no_grad in order to save memory.
        With torch.no_grad the method almost doesn't require extra memory
        for very large K.
        The method makes K independent passes through generator network,
        so the batch size is the same as for training with batch_vlb.
        """
        proposal, prior = self.make_latent_distributions(batch, mask)
        estimates = []
        for i in range(K):
            latent = proposal.rsample()

            rec_params = self.generative_network(latent)
            rec_loss = self.rec_log_prob(batch, rec_params, mask)

            prior_log_prob = prior.log_prob(latent)
            prior_log_prob = prior_log_prob.view(batch.shape[0], -1)
            prior_log_prob = prior_log_prob.sum(-1)

            proposal_log_prob = proposal.log_prob(latent)
            proposal_log_prob = proposal_log_prob.view(batch.shape[0], -1)
            proposal_log_prob = proposal_log_prob.sum(-1)

            estimate = rec_loss + prior_log_prob - proposal_log_prob
            estimates.append(estimate[:, None])

        return torch.logsumexp(torch.cat(estimates, 1), 1) - math.log(K)

    def generate_samples_params(self, batch, mask, K=1):
        """
        Generate parameters of generative distributions for samples
        from the given batch.
        It makes K latent representation for each object from the batch
        and generate samples from them.
        The second axis is used to index samples for an object, i. e.
        if the batch shape is [n x D1 x D2], then the result shape is
        [n x K x D1 x D2].
        It is better to use it inside torch.no_grad in order to save memory.
        With torch.no_grad the method doesn't require extra memory
        except the memory for the result.
        """
        _, prior = self.make_latent_distributions(batch, mask)
        samples_params = []
        for i in range(K):
            latent = prior.rsample()
            sample_params = self.generative_network(latent)
            samples_params.append(sample_params.unsqueeze(1))
        return torch.cat(samples_params, 1)

    def generate_reconstructions_params(self, batch, mask, K=1):
        """
        Generate parameters of generative distributions for reconstructions
        from the given batch.
        It makes K latent representation for each object from the batch
        and generate samples from them.
        The second axis is used to index samples for an object, i. e.
        if the batch shape is [n x D1 x D2], then the result shape is
        [n x K x D1 x D2].
        It is better to use it inside torch.no_grad in order to save memory.
        With torch.no_grad the method doesn't require extra memory
        except the memory for the result.
        """
        _, prior = self.make_latent_distributions(batch, mask)
        reconstructions_params = []
        for i in range(K):
            latent = prior.rsample()
            rec_params = self.generative_network(latent)
            reconstructions_params.append(rec_params.unsqueeze(1))
        return torch.cat(reconstructions_params, 1)

    def generate_probable_sample(self, state, mask):
        """
        Given a state and a mask, generate a probable smaple.
        This resembles class of methods from imputation networks,
        which are required for calculating Shapley values via our SVERL package.
        Parameters
        ----------
        state : array-like
            The observed state feature vector.
        mask : array-like
            Boolean mask indicating which features are observed (1) or unobserved (0).
        Returns
        -------
        sample : array-like
            Observed features remain, unobserved features sampled on-manifold by VAEAC.
        """
        mask = [1 - x for x in mask]
        mask = torch.tensor(mask, device='cpu').float().unsqueeze(0)

        if isinstance(state, np.ndarray):
            state = torch.tensor(state, device='cpu').float().unsqueeze(0)
        if state.get_device() != -1:
            print("Device for state is not CPU")
            state = state.cpu()
        if mask.get_device() != -1:
            print("Device for mask is not CPU")
            mask = mask.cpu()

        with torch.no_grad():            
            observed = self.make_observed(state, mask)            

            prior_params = self.prior_network(torch.cat([observed, mask],1).cpu())
            prior = normal_parse_params(prior_params, 1e-3)
            latent = prior.rsample()
            sample_params = self.generative_network(latent)
            sample = self.sampler_network(sample_params)
            sample = sample.squeeze(0).numpy()
            mask = mask.squeeze(0).numpy()
            state = state.squeeze(0).numpy()
        mask = [1 - x for x in mask]
        for i in range(len(sample)):
            if mask[i] == 1: 
                sample[i] = state[i]
        return sample
