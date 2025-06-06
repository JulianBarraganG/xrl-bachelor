import torch
import torch.nn as nn
import cma
from gymnasium import Env

import numpy as np

class PolicyCartpole(nn.Module):
    
    def __init__(self, state_space_dimension, action_space_dimension, num_neurons=5, bias = False):
        """
        Policy network for CartPole environment.

        Parameters
        ----------
        state_space_dimension : int 
        action_space_dimension : int
        num_neurons : int
            Number of neurons in the hidden layer.
        bias : bool
            Whether to include bias in the linear layers. Should be False for CartPole.
        """
        np.random.seed(0)
        torch.manual_seed(0)
        super(PolicyCartpole, self).__init__()
        self.state_space_dimension = state_space_dimension
        self.fc = nn.Linear(state_space_dimension, num_neurons, bias=bias)
        self.fc1 = nn.Linear(num_neurons, action_space_dimension, bias=bias)

    def forward(self, x: np.ndarray) -> int:
        """
        Forward pass through the network.
        
        Parameters
        ----------
        x : np.ndarray
            Input state feature vector.
        Returns
        -------
        int
            Action to be taken (0 or 1).
        """
        x = torch.Tensor( x.reshape((1, self.state_space_dimension)) )
        hidden = torch.tanh(self.fc(x))
        output = self.fc1(hidden)
        return int(output>0)
    
def fitness_cart_pole(x: np.ndarray, nn: torch.nn.Module, env: Env, mask: list[int]|None = None) -> float:
    """
    Returns negative accumulated reward for single pole, fully environment.

    Parameters
    ----------
    x : np.ndarray
        Parameter vector encoding the weights.
    nn : torch.nn.Module 
        Parameterized model.
    env : Env
        Environment ('CartPole-v?').
    mask : list|None, optional
    """
    torch.nn.utils.vector_to_parameters(torch.Tensor(x), nn.parameters())  # Set the policy parameters
    state = env.reset()[0]  # Forget about previous episode
    if mask is not None:
        mask = np.array(mask).astype(bool)
        state = state[mask]  # Convert mask to numpy array
    
    R = 0  # Accumulated reward
    while True:
        a = nn(state)        
        state, reward, terminated, truncated, _ = env.step(a)  # Simulate pole
        if mask is not None:
            state = state[mask]
        R += reward  # Accumulate 
        if truncated:
            return -1000  # Episode ended, final goal reached, we consider minimization
        if terminated:
            return -R  # Episode ended, we consider minimization
    return -R  # Never reached  

def train_cartpole_agent(policy_net , env, ftarget=-9999.9, mask=None):  
    """
    Function to train a policy network for the CartPole environment using CMA-ES.   
    
    Parameters
    ----------
    policy_net : PolicyCartpole 
        Policy network to be trained.
    env : Env
        CartPole environment.
    ftarget : float
        Target fitness value for CMA-ES. Default is -9999.9.
    Returns
    -------
    policy_net : PolicyCartpole
        Trained policy network.
    """   
    # Set the random seed for reproducibility
    np.random.seed(0)
    torch.manual_seed(0)

    d = sum(param.numel() for param in policy_net.parameters())
    initial_weights = np.random.normal(0, 0.01, d)  # Random parameters for initial policy, d denotes the number of weights
    initial_sigma = .01 # Initial global step-size sigma

    # Do the optimization
    cma_options = {'ftarget': ftarget, 'tolflatfitness':1000, 'eval_final_mean':False,
                   'verb_filenameprefix': '', 'verb_log': 0, 'verb_disp': 0}
    res = cma.fmin(fitness_cart_pole,  # Objective function
                initial_weights,  # Initial search point
                initial_sigma,  # Initial global step-size sigma
                args=([policy_net, env, mask]),  # Arguments passed to the fitness function
                   options=cma_options)
    env.close()
  
    # Set the policy parameters to the final solution
    torch.nn.utils.vector_to_parameters(torch.Tensor(res[0]), policy_net.parameters())      

    return policy_net  # Return the policy network

