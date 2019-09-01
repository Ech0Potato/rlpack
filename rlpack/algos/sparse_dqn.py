# -*- coding: utf-8 -*-
import numpy as np 
import tensorflow as tf 

from .base import Base 


class SparseDQN(Base):
    def __init__(self,
                 rnd=0,
                 dim_obs=None, n_act=None,
                 value_fn=None,
                 discount=0.99,
                 train_epoch=1, value_lr=1e-3,
                 update_target_rate=0.8, max_grad_norm=40,
                 save_path="./log", log_freq=10, save_model_freq=1000,
                 ):
        self._dim_obs = dim_obs
        self._n_act = n_act
        self._value_fn = value_fn

        self._discount = discount
        self._train_epoch = train_epoch
        self._value_lr = value_lr
        self._update_target_rate = update_target_rate
        self._max_grad_norm = max_grad_norm

        self._log_freq = log_freq
        self._save_model_freq = save_model_freq

        super().__init__(save_path=save_path, rnd=rnd)
        self.sess.run(self.init_target_op)

    def _build_network(self):
        """Build networks for algorithm."""
        self._obs = tf.placeholder(tf.float32, shape=[None, *self._dim_obs], name="observation")
        self._act = tf.placeholder(dtype=tf.int32, shape=[None], name="action")
        # self._reward = tf.placeholder(dtype=tf.float32, shape=[None], name="reward")
        # self._done = tf.placeholder(dtype=tf.float32, shape=[None], name="done")
        # self._obs2 = tf.placeholder(dtype=tf.float32, shape=[None, *self._dim_obs], name="next_observation")

        self._q_backup = tf.placeholder(tf.float32, shape=[None])
        # self.all_phs = [self._obs, self._act, self._reward, self._done, self._obs2]
        self.all_phs = [self._obs, self._act, self._q_backup]

        with tf.variable_scope("main/q"):
            self.q = self._value_fn(self._obs)

        with tf.variable_scope("target/q"):
            self.q_targ = self._value_fn(self._obs)

    def _build_algorithm(self):
        """Build networks for algorithm."""

        value_vars = tf.trainable_variables("main/q")

        # Compute the state value.
        batch_size = tf.shape(self._done)[0]
        action_index = tf.stack([tf.range(batch_size), self._act], axis=1)
        action_q = tf.gather_nd(self.q, action_index)

        # Compute back up.
        # q_backup = tf.stop_gradient(self._reward + self._discount * (1 - self._done) * tf.reduce_max(self.q_targ, axis=1))

        # Compute loss and optimize the object.
        # loss = tf.reduce_mean(tf.squared_difference(q_backup, action_q))   # 损失值。
        loss = tf.reduce_mean(tf.squared_difference(self._q_backup, action_q))   # 损失值。


        grads = tf.gradients(loss, value_vars)
        clipped_grads, _ = tf.clip_by_global_norm(grads, self._max_grad_norm)
        self._train_op = tf.train.AdamOptimizer(self._value_lr).apply_gradients(zip(clipped_grads, value_vars))

        # Update target network.
        def _update_target(net1, net2, rho=0):
            params1 = tf.trainable_variables(net1)
            params1 = sorted(params1, key=lambda v: v.name)
            params2 = tf.trainable_variables(net2)
            params2 = sorted(params2, key=lambda v: v.name)
            assert len(params1) == len(params2)
            update_ops = []
            for param1, param2 in zip(params1, params2):
                update_ops.append(param1.assign(rho*param1 + (1-rho)*param2))
            return update_ops

        self.update_target_op = _update_target("target/q", "main/q", rho=self._update_target_rate)
        self.init_target_op = _update_target("target/q", "main/q")

    def get_action(self, obs):
        q = self.sess.run(self.q, feed_dict={self._obs: obs})
        max_a = np.argmax(q, axis=1)
        return max_a

    def update(self, databatch):
        s_batch, a_batch, r_batch, d_batch, next_s_batch = databatch
        inputs = {k: v for k, v in zip(self.all_phs, [s_batch, a_batch, r_batch, d_batch, next_s_batch])}

        for _ in range(self._train_epoch):
            self.sess.run(self._train_op, feed_dict=inputs)

        self.sess.run(self.update_target_op)

        global_step, _ = self.sess.run([tf.train.get_global_step(), self.increment_global_step])

        if global_step % self._save_model_freq == 0:
            self.save_model()


    def spmax(self, q: np.ndarray) -> np.ndarray: 
        """sparse max operator. refer to equation (6) in https://arxiv.org/abs/1709.06293
        q: [batchsize, n_act]
        return: [batchsize] 
        """
        ordered_q = np.flip(np.sort(q, axis=-1), axis=-1)
        
        m, n = ordered_q.shape 
        res = np.zeros(m, dtype=np.float32)
        for i in range(m):
            s = 0
            for j in range(n):
                s += ordered_q[m, n]
                if 1 + (j+1) * ordered_q[m, n] <= s:
                    break 
            tau = (sum(ordered_q[i, :j+1]) - 1) / j
            res[i] = 0.5 * (sum(ordered_q[i, :j+1] ** 2) - tau * j) + 0.5
        return res 



