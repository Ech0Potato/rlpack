import numpy as np


class NChain(object):
    def __init__(self, N=20, slip_p=0.1):
        self.N = N
        self.slip_p = slip_p
        self.state = None

    def reset(self):
        self.state = 0
        s = np.zeros(self.N)
        s[self.state] = 1
        return s

    def step(self, a):
        """
        This game presents moves along a linear chain of states, with two actions:
        forward, which moves along the chain but returns no reward
        backward, which returns to the beginning and has a small reward
        The end of the chain, however, presents a large reward, and by moving 'forward' 
        at the end of the chain this large reward can be repeated.

        0: backward 
        1: forward 
        At each action, there is a small probability 0.1 that the agent 'slips' and the opposite transition is instead taken.
        """
        assert a in {0, 1}
        if a == 0:
            real_act = 0 if np.random.rand() > self.slip_p else 1
        elif a == 1:
            real_act = 1 if np.random.rand() > self.slip_p else 0
        else:
            assert False

        if real_act == 0:
            r = 0.01
            self.state = max(0, self.state-1)
        elif real_act == 1:
            r = 0
            self.state = min(self.N-1, self.state+1)
        else:
            assert False

        if self.state == self.N-1:
            r = 1

        s = np.zeros(self.N)
        s[self.state] = 1

        return s, r, False, None

    @property
    def dim_act(self):
        return 2

    @property
    def dim_obs(self):
        return (self.N,)


class GridWorld(object):
    def __init__(self, N=20, slip_p=0.1):
        self.N = N
        self.slip_p = slip_p
        self.state = (None, None)

    def reset(self):
        self.state = (0, 0)
        s = np.zeros((self.N, self.N), dtype=np.float32)
        s[self.state[0], self.state[1]] = 1
        return s

    def step(self, a):
        """
        a = 0: up
        a = 1: left 
        a = 2: down
        a = 3: right
        Given the action, move towards that direction with probability 0.7, 
        towards other direction with probability 0.1 repectively.
        A reward of 1 is given at position (20, 20).
        """
        assert a in {0, 1, 2, 3}
        if a == 0:
            rand_key = np.random.rand()
            if rand_key < 1 - self.slip_p * 3:
                real_act = 0
            elif rand_key < 1 - self.slip_p * 2:
                real_act = 1
            elif rand_key < 1 - self.slip_p * 1:
                real_act = 2
            else:
                real_act = 3
        elif a == 1:
            rand_key = np.random.rand()
            if rand_key < 1 - self.slip_p * 3:
                real_act = 1
            elif rand_key < 1 - self.slip_p * 2:
                real_act = 0
            elif rand_key < 1 - self.slip_p * 1:
                real_act = 2
            else:
                real_act = 3
        elif a == 2:
            rand_key = np.random.rand()
            if rand_key < 1 - self.slip_p * 3:
                real_act = 2
            elif rand_key < 1 - self.slip_p * 2:
                real_act = 0
            elif rand_key < 1 - self.slip_p * 1:
                real_act = 1
            else:
                real_act = 3
        else:
            rand_key = np.random.rand()
            if rand_key < 1 - self.slip_p * 3:
                real_act = 3
            elif rand_key < 1 - self.slip_p * 2:
                real_act = 0
            elif rand_key < 1 - self.slip_p * 1:
                real_act = 1
            else:
                real_act = 2

        if real_act == 0:
            self.state = (max(0, self.state[0] - 1), self.state[1])
        elif real_act == 1:
            self.state = (self.state[0], max(0, self.state[1] - 1))
        elif real_act == 2:
            self.state = (min(self.N - 1, self.state[0] + 1), self.state[1])
        elif real_act == 3:
            self.state = (self.state[0], min(self.N - 1, self.state[1] + 1))

        s = np.zeros((self.N, self.N), dtype=np.float32)
        s[self.state[0], self.state[1]] = 1

        if self.state == (self.N-1, self.N-1):
            r = 1
            d = True
        else:
            r = 0
            d = False

        return s, r, d, None

    @property
    def dim_obs(self):
        return (self.N, self.N)

    @property
    def dim_act(self):
        return 4


def make_toy(env_name):
    if env_name == "NChain":
        env = NChain(N=20, slip_p=0.1)
    elif env_name == "GridWorld":
        env = GridWorld()
