import tensorflow as tf

from .networker import Networker
from .tfestimator import TFEstimator
from . import utils


class A2C(TFEstimator):
    """Advantage Actor Critic."""

    def __init__(self, config): 
        super().__init__(config) 

    def _build_model(self):
        # Build inputs.
        self.observation = tf.placeholder(
            tf.float32, [None]+list(self.dim_ob), "observation")
        self.action = tf.placeholder(tf.float32, [None, self.dim_act], "action")
        self.span_reward = tf.placeholder(tf.float32, [None, 1], "span_reward")
        self.advantage = tf.placeholder(tf.float32, [None, 1], "advantage")

        self.old_mu = tf.placeholder(tf.float32, (None, self.dim_act), "old_mu")
        self.old_log_var = tf.placeholder(
            tf.float32, (self.dim_act,), "old_log_var")

        # Build Nets.
        with tf.variable_scope("gauss_net"):
            self.mu, self.log_var = Networker.build_gauss_net(self.observation, [64, 64, self.dim_act])

        with tf.variable_scope("value_net"):
            self.val = Networker.build_value_net(self.observation, [128, 64, 32, 1])

        # ------------ Compute g of object. -------------
        self.actor_vars = tf.trainable_variables("gauss_net")

        logp = -0.5 * tf.reduce_sum(self.log_var)
        logp += -0.5 * tf.reduce_sum(tf.square(self.action - self.mu) / tf.exp(self.log_var),
                                     axis=1,
                                     keepdims=True)

        logp_old = -0.5 * tf.reduce_sum(self.old_log_var)
        logp_old += -0.5 * tf.reduce_sum(tf.square(self.action - self.old_mu) / tf.exp(self.old_log_var),
                                         axis=1,
                                         keepdims=True)

        self.actor = -tf.reduce_mean(self.advantage * tf.exp(logp - logp_old))

        # Update by adam.
        self.train_actor_op = self.optimizer.minimize(
            self.actor, var_list=self.actor_vars)

        # ---------- Build critic algorithm. ----------
        self.critic_vars = tf.get_collection(
            tf.GraphKeys.TRAINABLE_VARIABLES, "value_net")

        self.critic_loss = tf.reduce_mean(
            tf.square(self.val - self.span_reward))

        # Update by adam.
        self.train_critic_op = self.critic_optimizer.minimize(
            self.critic_loss, global_step=tf.train.get_global_step(), var_list=self.critic_vars)

        # ---------- Build action. ----------
        self.sampled_act = (self.mu + tf.exp(self.log_var / 2.0)
                            * tf.random_normal(shape=[self.dim_act], dtype=tf.float32))

    def update(self, trajectories):

        data_batch = utils.trajectories_to_batch(trajectories, self.discount)

        old_mu_val, old_log_var_val = self.sess.run(
            [self.mu, self.log_var], feed_dict={self.observation: data_batch["state"]})

        # log_var is a common parameter independent of states.
        # So there is no shuffle for it.
        data_batch["oldmu"] = old_mu_val

        # ---------- Update actor ----------

        # Update actor.
        for _ in range(10):
            batch_generator = utils.generator(data_batch, self.batch_size)

            while True:
                try:
                    sample_batch = next(batch_generator)

                    # Compute advantage.
                    nextstate_val = self.sess.run(
                        self.val, feed_dict={self.observation: sample_batch["nextstate"]})
                    state_val = self.sess.run(
                        self.val, feed_dict={self.observation: sample_batch["state"]})

                    advantage = (sample_batch["reward"] + self.discount *
                                 (1 - sample_batch["done"]) * nextstate_val) - state_val

                    self.feeddict = {self.observation: sample_batch["state"],
                                     self.action: sample_batch["action"],
                                     self.span_reward: sample_batch["spanreward"],
                                     self.old_mu: sample_batch["oldmu"],
                                     self.old_log_var: old_log_var_val,
                                     self.advantage: advantage
                                     }

                    self.sess.run(self.train_actor_op, feed_dict=self.feeddict)
                except StopIteration:
                    del batch_generator
                    break

        # ---------- Update critic ----------
        critic_loss = self.sess.run(self.critic_loss, feed_dict=self.feeddict)
        print("old critic loss:", critic_loss)

        for _ in range(10):
            batch_generator = utils.generator(data_batch)

            while True:
                try:
                    sample_batch = next(batch_generator)

                    self.feeddict[self.observation] = sample_batch["state"]
                    self.feeddict[self.span_reward] = sample_batch["spanreward"]

                    _, total_t, critic_loss = self.sess.run(
                        [self.train_critic_op, tf.train.get_global_step(), self.critic_loss], feed_dict=self.feeddict)
                except StopIteration:
                    del batch_generator
                    break

        print("new critic loss:", critic_loss)

        return total_t, {"loss": critic_loss}

    def get_action(self, ob, epsilon=None):
        action = self.sess.run(self.sampled_act, feed_dict={
                               self.observation: ob})
        return action