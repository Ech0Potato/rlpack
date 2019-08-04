import math

import numpy as np
import tensorflow as tf

from ..common.utils import assert_shape
from .base import Base


class TRPO(Base):
    def __init__(self,
                 rnd=1,
                 n_env=1,
                 dim_obs=None,
                 dim_act=None,
                 discount=0.99,
                 save_path="./log",
                 save_model_freq=1000,
                 log_freq=1000,
                 trajectory_length=2048,
                 gae=0.95,
                 delta=0.01,
                 training_epoch=10,
                 max_grad_norm=40,
                 lr=3e-3):

        self.dim_obs = dim_obs
        self.dim_act = dim_act
        self.discount = discount
        self.delta = delta
        self.gae = gae

        self.trajectory_length = trajectory_length
        self.training_epoch = training_epoch
        self.max_grad_norm = max_grad_norm
        self.lr = lr

        self.save_model_freq = save_model_freq
        self.log_freq = log_freq

        super().__init__(save_path=save_path, rnd=rnd)

    def build_network(self):
        """Build networks for algorithm."""
        self.observation = tf.placeholder(tf.float32, [None, *self.dim_obs], "observation")

        with tf.variable_scope("policy_net"):
            x = tf.layers.dense(self.observation, 64, activation=tf.nn.tanh)
            x = tf.layers.dense(x, 64, activation=tf.nn.tanh)
            self.mu = tf.layers.dense(x, self.dim_act, activation=tf.tanh)
            self.log_var = tf.get_variable("log_var", [self.mu.shape.as_list()[1]], tf.float32, tf.constant_initializer(0.0))

        with tf.variable_scope("value_net"):
            x = tf.layers.dense(self.observation, 64, activation=tf.nn.tanh)
            x = tf.layers.dense(x, 64, activation=tf.nn.tanh)
            self.state_value = tf.squeeze(tf.layers.dense(x, 1, name="state_value"))

    def build_algorithm(self):
        """Build networks for algorithm."""
        self.critic_optimizer = tf.train.AdamOptimizer(self.lr)
        self.action = tf.placeholder(tf.float32, [None, self.dim_act], "action")
        self.old_mu = tf.placeholder(tf.float32, [None, self.dim_act], "old_mu")
        self.old_log_var = tf.placeholder(tf.float32, [self.dim_act], "old_var")
        self.advantage = tf.placeholder(tf.float32, [None], "advanatage")
        self.span_reward = tf.placeholder(tf.float32, [None], "span_reward")

        logp = -0.5 * tf.reduce_sum(self.log_var)
        logp += -0.5 * tf.reduce_sum(tf.square(self.action - self.mu) / tf.exp(self.log_var), axis=1)

        assert_shape(logp, [None])
        assert_shape(tf.square(self.action - self.mu) / tf.exp(self.log_var), [None, self.dim_act])

        logp_old = -0.5 * tf.reduce_sum(self.old_log_var)
        logp_old += -0.5 * tf.reduce_sum(tf.square(self.action - self.old_mu) / tf.exp(self.old_log_var), axis=1)

        assert_shape(logp_old, [None])

        self.obj = -tf.reduce_mean(self.advantage * tf.exp(logp - logp_old))

        # Compute gradients of object function.
        self.actor_vars = tf.trainable_variables("policy_net")
        self.g = self._flat_param_list(tf.gradients(self.obj, self.actor_vars))

        # Compute KL divergence.
        log_det_cov_old = tf.reduce_sum(self.old_log_var)
        log_det_cov_new = tf.reduce_sum(self.log_var)
        tr_old_new = tf.reduce_sum(tf.exp(self.old_log_var - self.log_var))

        self.kl = 0.5 * tf.reduce_mean(log_det_cov_new - log_det_cov_old + tr_old_new + tf.reduce_sum(tf.square(self.mu - self.old_mu) / tf.exp(self.log_var), axis=1) - self.dim_act)

        # Compute gradients of KL divergence.
        g_kl = self._flat_param_list(tf.gradients(self.kl, self.actor_vars))

        size_vec = np.sum([np.prod(v.shape.as_list()) for v in self.actor_vars])
        self.vec = tf.placeholder(tf.float32, [size_vec], "vector")
        # Add damping vector.
        self.Hv = self._flat_param_list(tf.gradients(tf.reduce_sum(g_kl * self.vec), self.actor_vars)) + 0.01 * self.vec

        self.critic_vars = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES, "value_net")
        self.critic_loss = tf.reduce_mean(tf.square(self.state_value - self.span_reward))
        grads = tf.gradients(self.critic_loss, self.critic_vars)
        clipped_grads, _ = tf.clip_by_global_norm(grads, self.max_grad_norm)
        self.train_critic_op = self.critic_optimizer.apply_gradients(zip(clipped_grads, self.critic_vars))
        # self.train_critic_op = self.critic_optimizer.minimize(self.critic_loss, var_list=self.critic_vars)

        # Build sample action.
        self.n_output_action = tf.placeholder(tf.int32)
        self.sample_action = self.mu + tf.exp(self.log_var / 2.0) * tf.random_normal(shape=[self.n_output_action, self.dim_act], dtype=tf.float32)

    def update(self, minibatch, update_ratio):
        """Update the algorithm by suing a batch of data.

        Parameters:
            - minibatch: A list of ndarray containing a minibatch of state, action, reward, done.

                - state shape: (n_env, batch_size+1, state_dimension)
                - action shape: (n_env, batch_size, state_dimension)
                - reward shape: (n_env, batch_size)
                - done shape: (n_env, batch_size)

            - update_ratio: float scalar in (0, 1).

        Returns:
            - training infomation.
        """
        s_batch, a_batch, r_batch, d_batch = minibatch
        assert s_batch.shape == (self.n_env, self.trajectory_length + 1, *self.dim_obs)

        advantage_batch = np.empty([self.n_env, self.trajectory_length], dtype=np.float32)
        target_value_batch = np.empty([self.n_env, self.trajectory_length], dtype=np.float32)

        for i in range(self.n_env):
            state_value_batch = self.sess.run(self.state_value, feed_dict={self.observation: s_batch[i, ...]})
            delta_value_batch = r_batch[i, :] + self.discount * (1 - d_batch[i, :]) * state_value_batch[1:] - state_value_batch[:-1]
            assert state_value_batch.shape == (self.trajectory_length + 1,)
            assert delta_value_batch.shape == (self.trajectory_length,)

            last_advantage = 0
            for t in reversed(range(self.trajectory_length)):
                advantage_batch[i, t] = delta_value_batch[t] + self.discount * self.gae * (1 - d_batch[i, t]) * last_advantage
                last_advantage = advantage_batch[i, t]

            target_value_batch[i, :] = state_value_batch[:-1] + advantage_batch[i, :]

        s_batch = s_batch[:, :-1, ...].reshape(self.n_env * self.trajectory_length, *self.dim_obs)
        a_batch = a_batch.reshape(self.n_env * self.trajectory_length, self.dim_act)
        advantage_batch = advantage_batch.reshape(self.n_env * self.trajectory_length)
        target_value_batch = target_value_batch.reshape(self.n_env * self.trajectory_length)

        # Normalize advantage.
        advantage_batch = (advantage_batch - advantage_batch.mean()) / (advantage_batch.std() + 1e-10)

        # Compute some values on old parameters.
        old_mu_batch, old_log_var = self.sess.run([self.mu, self.log_var], feed_dict={self.observation: s_batch})

        # ----------------- Update actor -------------------
        # Fill feed_dict.
        self.feed_dict = {self.observation: s_batch,
                          self.action: a_batch,
                          self.span_reward: target_value_batch,
                          self.old_mu: old_mu_batch,
                          self.old_log_var: old_log_var,
                          self.advantage: advantage_batch}

        # Compute update direction.
        g_obj = self.sess.run(self.g, feed_dict={self.observation: s_batch, self.action: a_batch, self.advantage: advantage_batch, self.old_mu: old_mu_batch, self.old_log_var: old_log_var})

        step_direction = self._conjudate_gradient(-g_obj)  # pylint: disable=E1130

        # Compute max step length.
        self.feed_dict[self.vec] = step_direction
        Mx = self.sess.run(self.Hv, feed_dict=self.feed_dict)
        max_step_length = np.sqrt(self.delta / (0.5 * np.dot(step_direction, Mx)))

        # Line search to update theta.
        old_theta = self.sess.run(self._flat_param_list(self.actor_vars))
        theta, _ = self._line_search(old_theta, step_direction, max_step_length, self._target_func, max_backtrack=5)

        # Assign theta to actor parameters.
        self._recover_param_list(theta)

        # ------------------ Update Critic ----------------------
        for _ in range(self.training_epoch):
            self.sess.run(self.train_critic_op, feed_dict={self.observation: s_batch, self.span_reward: target_value_batch})

            # batch_generator = self._generator([s_batch, a_batch, advantage_batch, old_mu_batch, target_value_batch], batch_size=self.batch_size)
            # while True:
            #     try:
            #         mb_s, mb_a, mb_advantage, mb_old_mu, mb_target_value = next(batch_generator)
            #         self.sess.run(self.train_critic_op, feed_dict={self.observation: mb_s, self.span_reward: mb_target_value})
            #     except StopIteration:
            #         break

        # Save model.
        global_step, _ = self.sess.run([tf.train.get_global_step(), self.increment_global_step])
        if global_step % self.save_model_freq == 0:
            self.save_model()

    def _target_func(self, theta):
        self._recover_param_list(theta)
        return self.sess.run([self.obj, self.kl], feed_dict=self.feed_dict)

    def _line_search(self, old_theta, step_dir, step_len, target_func, max_backtrack=10):
        fval = target_func(old_theta)[0]
        for i in range(max_backtrack):
            step_frac = 0.5 ** i
            theta = step_frac * step_len * step_dir + old_theta
            new_fval, new_kl = target_func(theta)
            if new_kl > 1e-2:
                new_fval += np.inf
            actual_improve = fval - new_fval
            if actual_improve > 0:
                return theta, True
        return old_theta, False

    def _flat_param_list(self, ts):
        return tf.concat([tf.reshape(t, [-1]) for t in ts], axis=0)

    def _recover_param_list(self, ts):
        res = []
        start = 0
        for param in self.actor_vars:
            shape = param.shape.as_list()
            param_np = np.reshape(ts[start: start + np.prod(shape)], shape)
            res.append(param_np)
            start += np.prod(shape)

        assign_weight_op = [x.assign(y) for x, y in zip(self.actor_vars, res)]
        self.sess.run(assign_weight_op)

    def _conjudate_gradient(self, g, residual_tol=1e-8, cg_damping=0.1):
        x = np.zeros_like(g)
        p = g.copy()
        r = -g.copy()

        for _ in range(10):
            self.feed_dict[self.vec] = p
            Ap = self.sess.run(self.Hv, feed_dict=self.feed_dict)

            alpha = np.dot(r, r) / np.dot(p, Ap)
            x = x + alpha * p
            r_new = r + alpha * Ap
            beta = np.dot(r_new, r_new) / np.dot(r, r)
            p = -r_new + beta * p
            r = r_new

            if np.dot(r, r) < residual_tol:
                break
        return x

    def _generator(self, data_batch, batch_size=32):
        n_sample = data_batch[0].shape[0]
        assert n_sample == self.n_env * self.trajectory_length

        index = np.arange(n_sample)
        np.random.shuffle(index)

        for i in range(math.ceil(n_sample / batch_size)):
            span_index = slice(i * batch_size, min((i + 1) * batch_size, n_sample))
            span_index = index[span_index]
            yield [x[span_index] if x.ndim == 1 else x[span_index, :] for x in data_batch]

    def get_action(self, obs):
        """Return actions according to the given observation.

        Parameters:
            - ob: An ndarray with shape (n, state_dimension).

        Returns:
            - An ndarray for action with shape (n, action_dimension).
        """
        n = obs.shape[0]
        actions = self.sess.run(self.sample_action, feed_dict={self.observation: obs, self.n_output_action: n})
        return actions
