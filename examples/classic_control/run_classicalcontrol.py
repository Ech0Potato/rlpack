# -*- coding: utf-8 -*-


import argparse
import time
from collections import namedtuple

import gym
import numpy as np
import tensorflow as tf

from rlpack.algos import DQN, DoubleDQN, DuelDQN, DistDQN
from rlpack.utils import mlp

parser = argparse.ArgumentParser(description='set parameter.')
parser.add_argument('--env',  type=str, default="CartPole-v1")
args = parser.parse_args()

env = gym.make(args.env)
dim_obs = env.observation_space.shape
n_act = env.action_space.n
epsilon = 0.1
max_ep_len = 1000


class ReplayBuffer:
    """
    A simple FIFO experience replay buffer for TD3 agents.
    """

    def __init__(self, dim_obs, n_act, size):
        self.obs1_buf = np.zeros([size, *dim_obs], dtype=np.float32)
        self.obs2_buf = np.zeros([size, *dim_obs], dtype=np.float32)
        self.acts_buf = np.zeros([size], dtype=np.int32)
        self.rews_buf = np.zeros(size, dtype=np.float32)
        self.done_buf = np.zeros(size, dtype=np.float32)
        self.ptr, self.size, self.max_size = 0, 0, size

    def store(self, obs, act, rew, next_obs, done):
        self.obs1_buf[self.ptr] = obs
        self.obs2_buf[self.ptr] = next_obs
        self.acts_buf[self.ptr] = act
        self.rews_buf[self.ptr] = rew
        self.done_buf[self.ptr] = done
        self.ptr = (self.ptr+1) % self.max_size
        self.size = min(self.size+1, self.max_size)

    def sample_batch(self, batch_size=32):
        idxs = np.random.randint(0, self.size, size=batch_size)
        return dict(obs1=self.obs1_buf[idxs],
                    obs2=self.obs2_buf[idxs],
                    acts=self.acts_buf[idxs],
                    rews=self.rews_buf[idxs],
                    done=self.done_buf[idxs])


# def duel_value_fn(x):
#     net = mlp(x, [64, 64], activation=tf.nn.relu)
#     v = mlp(net, [1], activation=tf.nn.relu)
#     adv = mlp(net, [n_act], activation=tf.nn.relu)
#     return v, adv

# def value_fn(x):
#     v = mlp(x, [64, 64, n_act], activation=tf.nn.relu)
#     return v


def distdqn_policy_fn(x):
    logit = mlp(x, [64, 64, n_act*51], activation=tf.nn.relu)
    return logit


def run_main():

    # agent = DQN(n_act=n_act, dim_obs=dim_obs, value_fn=value_fn, save_path="./log/classicalcontrol/dqn")
    # agent = DoubleDQN(n_act=n_act, dim_obs=dim_obs, value_fn=value_fn, save_path="./log/classicalcontrol/doubledqn")
    # agent = DuelDQN(n_act=n_act, dim_obs=dim_obs, value_fn=duel_value_fn, save_path="./log/classicalcontrol/dueldqn")
    agent = DistDQN(n_act=n_act, dim_obs=dim_obs, policy_fn=distdqn_policy_fn, save_path="./log/classicalcontrol/distdqn")
    replay_buffer = ReplayBuffer(dim_obs=dim_obs, n_act=n_act, size=int(1e6))

    start_time = time.time()
    o, ep_ret, ep_len = env.reset(), 0, 0
    for epoch in range(50):
        ep_ret_list, ep_len_list = [], []
        for t in range(1000):
            a = agent.get_action(o[np.newaxis, :])[0]
            if np.random.rand() < epsilon:
                a = np.random.randint(n_act)

            nexto, r, d, _ = env.step(a)
            ep_ret += r
            ep_len += 1

            replay_buffer.store(o, a, r, nexto, int(d))

            o = nexto

            terminal = d or (ep_len == max_ep_len)
            if terminal or (t == 1000-1):

                for _ in range(ep_len):
                    batch = replay_buffer.sample_batch(100)
                    agent.update([batch["obs1"], batch["acts"], batch["rews"], batch["done"], batch["obs2"]])

                if not(terminal):
                    print('Warning: trajectory cut off by epoch at %d steps.' % ep_len)
                if terminal:
                    # 当到达完结状态或是最长状态时，记录结果
                    ep_ret_list.append(ep_ret)
                    ep_len_list.append(ep_len)
                o, ep_ret, ep_len = env.reset(), 0, 0

        print(f"{epoch}th epoch. average_return={np.mean(ep_ret_list)}, average_len={np.mean(ep_len_list)}")

        agent.add_scalar("average_return", np.mean(ep_ret_list), epoch*1000)
        agent.add_scalar("average_length", np.mean(ep_len_list), epoch*1000)

    elapsed_time = time.time() - start_time
    print("elapsed time:", elapsed_time)


if __name__ == "__main__":
    run_main()
