# imports and basic notebook setup
import os
from cStringIO import StringIO
import matplotlib as mpl
mpl.use('Agg')
import numpy as np
import scipy.ndimage as nd
import PIL.Image
from google.protobuf import text_format
import sys

pending_img_path  = '/var/www/deepdream/deepdream/static/pending/'
final_img_path = "/var/www/deepdream/deepdream/static/final/"
original_img_path =  "/var/www/deepdream/deepdream/static/originals/"

pending_files = os.listdir(pending_img_path)
if not len(pending_files):
	print "no files"
	exit(0)

import caffe

model_path = '/home/ubuntu/caffe/models/bvlc_googlenet/' # substitute your path here
net_fn   = model_path + 'deploy.prototxt'
param_fn = model_path + 'bvlc_googlenet.caffemodel'

# Patching model to be able to compute gradients.
# Note that you can also manually add "force_backward: true" line to "deploy.prototxt".
model = caffe.io.caffe_pb2.NetParameter()
text_format.Merge(open(net_fn).read(), model)
model.force_backward = True
open('tmp.prototxt', 'w').write(str(model))

net = caffe.Classifier('tmp.prototxt', param_fn,
					   mean = np.float32([104.0, 116.0, 122.0]), # ImageNet mean, training set dependent
					   channel_swap = (2,1,0)) # the reference model has channels in BGR order instead of RGB

def saveImage(k, vis):
	outputPath = k+".jpeg"
	result = PIL.Image.fromarray(np.uint8(vis))
	result.save(outputPath)
	return outputPath		

# a couple of utility functions for converting to and from Caffe's input image layout
def preprocess(net, img):
    return np.float32(np.rollaxis(img, 2)[::-1]) - net.transformer.mean['data']
def deprocess(net, img):
    return np.dstack((img + net.transformer.mean['data'])[::-1])


def make_step(net, step_size=1.5, end='inception_4c/output', jitter=32, clip=True):
    '''Basic gradient ascent step.'''

    src = net.blobs['data'] # input image is stored in Net's 'data' blob
    dst = net.blobs[end]

    ox, oy = np.random.randint(-jitter, jitter+1, 2)
    src.data[0] = np.roll(np.roll(src.data[0], ox, -1), oy, -2) # apply jitter shift
            
    net.forward(end=end)
    dst.diff[:] = dst.data  # specify the optimization objective
    net.backward(start=end)
    g = src.diff[0]
    # apply normalized ascent step to the input image
    src.data[:] += step_size/np.abs(g).mean() * g

    src.data[0] = np.roll(np.roll(src.data[0], -ox, -1), -oy, -2) # unshift image
            
    if clip:
        bias = net.transformer.mean['data']
        src.data[:] = np.clip(src.data, -bias, 255-bias)



def deepdream(net, base_img, iter_n=10, octave_n=4, octave_scale=1.4, end='inception_4c/output', clip=True, **step_params):
    # prepare base images for all octaves
    
    visualizations = []
    octaves = [preprocess(net, base_img)]
    for i in xrange(octave_n-1):
        octaves.append(nd.zoom(octaves[-1], (1, 1.0/octave_scale,1.0/octave_scale), order=1))
    
    src = net.blobs['data']
    detail = np.zeros_like(octaves[-1]) # allocate image for network-produced details
    for octave, octave_base in enumerate(octaves[::-1]):
        h, w = octave_base.shape[-2:]
        if octave > 0:
            # upscale details from the previous octave
            h1, w1 = detail.shape[-2:]
            detail = nd.zoom(detail, (1, 1.0*h/h1,1.0*w/w1), order=1)

        src.reshape(1,3,h,w) # resize the network's input image size
        src.data[0] = octave_base+detail
        for i in xrange(iter_n):
            make_step(net, end=end, clip=clip, **step_params)
            
            # visualization
            vis = deprocess(net, src.data[0])
            if not clip: # adjust image contrast if clipping is disabled
                vis = vis*(255.0/np.percentile(vis, 99.98))
            k = "octave_"+str(octave)+"-iter_"+str(i)+"-layer_"+end.replace("/", "_")
            #saveImage(k, vis)
            print octave, i, end, vis.shape
            #clear_output(wait=True)
            
        # extract details produced on the current octave
        detail = src.data[0]-octave_base
    # returning the resulting image
    return deprocess(net, src.data[0])


original_img = pending_files[0]
path = pending_img_path + original_img

#compress if image is too large
compressed_path = path.split(".")[0]+"_1."+path.split(".")[1]
if os.path.getsize(path) > 700000:
    foo = PIL.Image.open(path)
    foo.save(compressed_path , optimize=True,quality=50)
    os.rename(compressed_path, path)

img = np.float32(PIL.Image.open(path))
os.rename(pending_img_path+original_img, original_img_path +original_img)

dream = deepdream(net, img) 
final_img = original_img.split(".")[0].split("/")[-1]
out_path = saveImage(final_img_path+final_img, dream)


