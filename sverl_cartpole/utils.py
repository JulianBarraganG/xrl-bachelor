import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from tqdm import tqdm, trange

import numpy as np

class StateFeatureDataset(Dataset):
    def __init__(self, data):
        self.data = torch.FloatTensor(data)  # Convert to PyTorch tensor

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        return self.data[idx]
    
    
    
#Gets all subsets of masks when one feature is fixed to 0.
#Basically all C \in F/i 

def get_all_subsets(fixed_features, list_length):
    """
    Generate all binary lists of given length with certain positions fixed to 0.
    
    Args:
        fixed_features: List of indices that must be 0 in all variations
        list_length: Total length of the binary lists to generate
        
    Returns:
        List of all possible binary lists with the specified features fixed to 0
    """
    variations = []
    
    # Calculate how many bits we need to vary (total length minus fixed positions)
    variable_positions = [pos for pos in range(list_length) if pos not in fixed_features]
    num_variable_bits = len(variable_positions)
    
    # Generate all possible combinations for the variable bits
    for num in range(2 ** num_variable_bits):
        binary = [0] * list_length
        
        # Fill in the variable positions
        for bit_pos in range(num_variable_bits):
            # Get the current variable position in the original list
            original_pos = variable_positions[bit_pos]
            # Get the bit value (0 or 1)
            bit_value = (num >> (num_variable_bits - 1 - bit_pos)) & 1
            binary[original_pos] = bit_value
            
        variations.append(binary)
    
    return variations


def get_trajectory(policy, env, time_horizon = 10**3): 
    trajectory_features = []  # Store the features of the trajectory
    state = env.reset()[0]  # Forget about previous episode
    state_space_dimension = env.observation_space.shape[0]  # State space dimension
    
    
    for _ in trange(time_horizon):     

        a = policy(state)
        
        state, reward, terminated, truncated, _ = env.step(a)
        if(terminated or truncated): 
            state = env.reset()[0]
            
        trajectory_features.append(state)   
        
        
    return np.array(trajectory_features)


def evaluate_policy(no_episodes, env, policy): 
    rewards = []
    for _ in trange(no_episodes):
        R = 0
        state = env.reset()[0]
        while True:  # Environment sets "truncated" to true after 500 steps 
                state, reward, terminated, truncated, _ = env.step( policy(state) ) #  Take a  action
                R += reward  # Accumulate reward
                if terminated or truncated:
                    break
        env.close()
        rewards.append(R)
    return np.array(rewards)  # Return the cumulated reward
        