import argparse
from collections import deque
import gym
import numpy as np
from tqdm import tqdm
import tensorflow as tf

from rlpack.algos import PPO


parser = argparse.ArgumentParser(description="Parse environment name.")
parser.add_argument("--env", type=str, default="CartPole-v1")
parser.add_argument("--niter", type=int, default=1000)
parser.add_argument("--batchsize", type=int, default=128)
args = parser.parse_args()


env = gym.make(args.env)


def trajectory(env, agent):
    t = deque()
    s = env.reset()
    tsum = 0
    while True:
        a = agent.get_action(s[np.newaxis, :])[0]
        ns, r, d, _ = env.step(a)
        t.append((s, a, r))
        s = ns
        tsum += r
        if d is True:
            break
    return t, tsum


def obs_fn():
    obs = tf.placeholder(shape=[None, *env.observation_space.shape], dtype=tf.float32, name="observation")
    return obs


def policy_fn(obs):
    x = tf.layers.dense(obs, units=128, activation=tf.nn.relu)
    x = tf.layers.dense(x, units=128, activation=tf.nn.relu)
    x = tf.layers.dense(x, units=64, activation=tf.nn.relu)
    x = tf.layers.dense(x, units=env.action_space.n, activation=None)
    return x


def value_fn(obs):
    x = tf.layers.dense(obs, units=128, activation=tf.nn.relu)
    x = tf.layers.dense(x, units=128, activation=tf.nn.relu)
    x = tf.layers.dense(x, units=64, activation=tf.nn.relu)
    x = tf.layers.dense(x, units=1)
    x = tf.squeeze(x)
    return x


def run_main():

    agent = PPO(dim_obs=env.observation_space.shape,
                policy_fn=policy_fn,
                value_fn=value_fn,
                dim_act=env.action_space.n,
                clip_schedule=lambda x: 0.1,
                lr_schedule=lambda x: 1e-4,
                train_epoch=10,
                batch_size=args.batchsize,
                log_freq=10,
                save_path="./log/ppo_cc",
                save_model_freq=1000)
    totrew = 0
    for i in tqdm(range(args.niter)):
        traj_list = deque()
        totrew_list = deque()
        for _ in range(10):
            traj, totrew = trajectory(env, agent)
            traj_list.append(traj)
            totrew_list.append(totrew)
        agent.add_scalar("ppo/totrew", np.mean(totrew_list), i)
        agent.update(traj_list)
        tqdm.write(f"{i}th. len={np.mean([len(t) for t in traj_list])}")


def run_game():
    s = env.reset()
    totrew = 0
    for i in range(100):
        a = np.random.randint(2)
        ns, r, d, _ = env.step(a)
        s = ns
        totrew += r
        if d is True:
            s = env.reset()


if __name__ == "__main__":
    run_main()
