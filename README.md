# Continuous SVERL-P (Bachelor's thesis)

This repository implements a framework for calculating Shapley values using the SVERL-P method from [Beechey et. al 2023](https://arxiv.org/pdf/2306.05810) in continuous environments using imputation functions [VAEAC](https://arxiv.org/pdf/1806.02382) and [Neural Conditioner](https://arxiv.org/pdf/1902.08401)

## Running experiments 

### run_cartpole.py
Running the script run_cartpole.py will calculate Shapley values for each feature via model-retraining. The policy with full observability will be saved in /models. Trajectories will be calculated using this policy, saved in /data, and a VAEAC and NC model will be trained on these. Then Shapley values will be calculated using the SVERL-P method modified for continuous environments, using these two imputation functions, as well as a uniform sampler (which samples from the state space) and a policy sampler (which samples from the trajectories). These imputation functions will be saved in /imputation_models. 

The results of the characteristic functions for each method is saved in /characteristic_dicts to make the calculation of Shapley values faster. 

The Shapley values are saved in .csv files in /data, the plots are saved in /plots. 

To rerun the experiment, delete the parts you wish to rerun. I.e. if you wish to rerun everything, delete /models, /imputation_models, /characteristic_dicts and the trajectories saved in /data. 

If you want to retrain the imputation functions only, delete /imputation_models and their characteristic function dictionairies in /characteristic_dicts. 

### run_lunarlander.py 

Need to merge two branches first. 