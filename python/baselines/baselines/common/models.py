import numpy as np
import tensorflow as tf
from baselines.a2c import utils
from baselines.a2c.utils import conv, fc, conv_to_fc, batch_to_seq, seq_to_batch
from baselines.common.mpi_running_mean_std import RunningMeanStd
import tensorflow.contrib.layers as layers


def nature_cnn(unscaled_images, **conv_kwargs):
    """
    CNN from Nature paper.
    """
    scaled_images = tf.cast(unscaled_images, tf.float32) / 255.
    activ = tf.nn.relu
    h = activ(conv(scaled_images, 'c1', nf=32, rf=8, stride=4, init_scale=np.sqrt(2),
                   **conv_kwargs))
    h2 = activ(conv(h, 'c2', nf=64, rf=4, stride=2, init_scale=np.sqrt(2), **conv_kwargs))
    h3 = activ(conv(h2, 'c3', nf=64, rf=3, stride=1, init_scale=np.sqrt(2), **conv_kwargs))
    h3 = conv_to_fc(h3)
    return activ(fc(h3, 'fc1', nh=512, init_scale=np.sqrt(2)))


def mlp(num_layers=2, num_hidden=64, activation= tf.tanh): #tf.nn.relu):
    """
    Simple fully connected layer policy. Separate stacks of fully-connected layers are used for policy and value function estimation.
    More customized fully-connected policies can be obtained by using PolicyWithV class directly.

    Parameters:
    ----------

    num_layers: int                 number of fully-connected layers (default: 2)
    
    num_hidden: int                 size of fully-connected layers (default: 64)
    
    activation:                     activation function (default: tf.tanh)
        
    Returns:
    -------

    function that builds fully connected network with a given input placeholder
    """        
    def network_fn(X):
        hidden_layer_sizes = [64, 64] #[num_hidden] * num_layers # [128,128] # [256, 256]
        activations = [tf.nn.relu, tf.nn.relu] # [tf.nn.tanh, tf.nn.tanh]
        print("Used network size is {} with activation {}".format(hidden_layer_sizes,
                                                                  str(activation if activation is None else activations)))
        h = tf.layers.flatten(X)
        for i in range(num_layers):
            h = activations[i](fc(h, 'mlp_fc{}'.format(i), nh=hidden_layer_sizes[i], init_scale=np.sqrt(2)))
        return h, None

    return network_fn
  

def cnn(**conv_kwargs):
    def network_fn(X):
        return nature_cnn(X, **conv_kwargs), None
    return network_fn

def cnn_small(**conv_kwargs):
    def network_fn(X):
        h = tf.cast(X, tf.float32) / 255.
        
        activ = tf.nn.relu
        h = activ(conv(h, 'c1', nf=8, rf=8, stride=4, init_scale=np.sqrt(2), **conv_kwargs))
        h = activ(conv(h, 'c2', nf=16, rf=4, stride=2, init_scale=np.sqrt(2), **conv_kwargs))
        h = conv_to_fc(h)
        h = activ(fc(h, 'fc1', nh=128, init_scale=np.sqrt(2)))
        return h, None
    return network_fn



def lstm(nlstm=128, layer_norm=False):
    def network_fn(X, nenv=1):
        nbatch = X.shape[0] 
        nsteps = nbatch // nenv
         
        h = tf.layers.flatten(X)

        M = tf.placeholder(tf.float32, [nbatch]) #mask (done t-1)
        S = tf.placeholder(tf.float32, [nenv, 2*nlstm]) #states

        xs = batch_to_seq(h, nenv, nsteps)
        ms = batch_to_seq(M, nenv, nsteps)

        if layer_norm:
            h5, snew = utils.lnlstm(xs, ms, S, scope='lnlstm', nh=nlstm)
        else:
            h5, snew = utils.lstm(xs, ms, S, scope='lstm', nh=nlstm)
            
        h = seq_to_batch(h5)
        initial_state = np.zeros(S.shape.as_list(), dtype=float)

        return h, {'S':S, 'M':M, 'state':snew, 'initial_state':initial_state}

    return network_fn


def cnn_lstm(nlstm=128, layer_norm=False, **conv_kwargs):
    def network_fn(X, nenv=1):
        nbatch = X.shape[0] 
        nsteps = nbatch // nenv
         
        h = nature_cnn(X, **conv_kwargs)
       
        M = tf.placeholder(tf.float32, [nbatch]) #mask (done t-1)
        S = tf.placeholder(tf.float32, [nenv, 2*nlstm]) #states

        xs = batch_to_seq(h, nenv, nsteps)
        ms = batch_to_seq(M, nenv, nsteps)

        if layer_norm:
            h5, snew = utils.lnlstm(xs, ms, S, scope='lnlstm', nh=nlstm)
        else:
            h5, snew = utils.lstm(xs, ms, S, scope='lstm', nh=nlstm)
            
        h = seq_to_batch(h5)
        initial_state = np.zeros(S.shape.as_list(), dtype=float)

        return h, {'S':S, 'M':M, 'state':snew, 'initial_state':initial_state}

    return network_fn

def cnn_lnlstm(nlstm=128, **conv_kwargs):
    return cnn_lstm(nlstm, layer_norm=True, **conv_kwargs)


def conv_only(convs=[(32, 8, 4), (64, 4, 2), (64, 3, 1)], **conv_kwargs):
    ''' 
    convolutions-only net

    Parameters:
    ----------

    conv:       list of triples (filter_number, filter_size, stride) specifying parameters for each layer. 

    Returns:

    function that takes tensorflow tensor as input and returns the output of the last convolutional layer
    
    '''

    def network_fn(X):
        out = tf.cast(X, tf.float32) / 255.
        with tf.variable_scope("convnet"):
            for num_outputs, kernel_size, stride in convs:
                out = layers.convolution2d(out,
                                           num_outputs=num_outputs,
                                           kernel_size=kernel_size,
                                           stride=stride,
                                           activation_fn=tf.nn.relu,
                                           **conv_kwargs)

        return out, None
    return network_fn

def _normalize_clip_observation(x, clip_range=[-5.0, 5.0]):
    rms = RunningMeanStd(shape=x.shape[1:])
    norm_x = tf.clip_by_value((x - rms.mean) / rms.std, min(clip_range), max(clip_range))
    return norm_x, rms
    

def get_network_builder(name):
    # TODO: replace with reflection? 
    if name == 'cnn':
        return cnn
    elif name == 'cnn_small':
        return cnn_small
    elif name == 'conv_only':
        return conv_only
    elif name == 'mlp':
        return mlp
    elif name == 'lstm':
        return lstm
    elif name == 'cnn_lstm':
        return cnn_lstm
    elif name == 'cnn_lnlstm':
        return cnn_lnlstm
    else:
        raise ValueError('Unknown network type: {}'.format(name))
