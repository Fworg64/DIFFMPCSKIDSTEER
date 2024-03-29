import torch

from mpc import mpc
from mpc.mpc import QuadCost, LinDx, GradMethods
#from mpc.env_dx import pendulum
from mymodels import skidsteer

import numpy as np
import numpy.random as npr

import matplotlib.pyplot as plt

import os
import io
import base64
import tempfile
from IPython.display import HTML

from tqdm import tqdm

from time import gmtime, strftime

#params = torch.tensor((10., 1., 1.))
dx = skidsteer.SkidSteerDx(simple=True)

n_batch, T, mpc_T = 16, 60, 20

def uniform(shape, low, high):
    r = high-low
    return torch.rand(shape)*r+low

torch.manual_seed(0)
x = uniform(n_batch, -.05, .05)
y = uniform(n_batch, -.5, .5)
th = uniform(n_batch, -.15, .15)
xinit = torch.stack((x, y, th), dim=1)

x = xinit
u_init = None

# The cost terms for the swingup task can be alternatively obtained
# for this pendulum environment with:
# q, p = dx.get_true_obj()

mode = 'swingup'
# mode = 'spin'

if mode == 'swingup':
    goal_weights = torch.Tensor((1.5, 1.5, 1.))
    goal_state = torch.Tensor((2., 1. ,0.))
    ctrl_penalty = 0.001
    q = torch.cat((
        goal_weights,
        ctrl_penalty*torch.ones(dx.n_ctrl)
    ))
    px = -torch.sqrt(goal_weights)*goal_state
    p = torch.cat((px, torch.zeros(dx.n_ctrl)))
    Q = torch.diag(q).unsqueeze(0).unsqueeze(0).repeat(
        mpc_T, n_batch, 1, 1
    )
    p = p.unsqueeze(0).repeat(mpc_T, n_batch, 1)
elif mode == 'spin':
    Q = 0.001*torch.eye(dx.n_state+dx.n_ctrl).unsqueeze(0).unsqueeze(0).repeat(
        mpc_T, n_batch, 1, 1
    )
    p = torch.tensor((0., 0., -1., 0.))
    p = p.unsqueeze(0).repeat(mpc_T, n_batch, 1)

t_dir = tempfile.mkdtemp()
print('Tmp dir: {}'.format(t_dir))

x_rec =[x]
cum_cost = 0;

for t in tqdm(range(T)):
    nominal_states, nominal_actions, nominal_objs = mpc.MPC(
        dx.n_state, dx.n_ctrl, mpc_T,
        u_init=u_init,
        u_lower=dx.lower, u_upper=dx.upper,
        lqr_iter=50,
        verbose=0,
        exit_unconverged=False,
        detach_unconverged=False,
        linesearch_decay=dx.linesearch_decay,
        max_linesearch_iter=dx.max_linesearch_iter,
        grad_method=GradMethods.AUTO_DIFF,
        eps=1e-2,
    )(x, QuadCost(Q, p), dx)
    
    next_action = nominal_actions[0]
    u_init = torch.cat((nominal_actions[1:], torch.zeros(1, n_batch, dx.n_ctrl)), dim=0)
    u_init[-2] = u_init[-3]
    x = dx(x, next_action)

    #print(x)
    for row in x:
      cum_cost = cum_cost + torch.norm(row - goal_state)

    x_rec.append(x)
    n_row, n_col = 4, 4
    fig, axs = plt.subplots(n_row, n_col, figsize=(3*n_col,3*n_row))
    axs = axs.reshape(-1)
    for i in range(n_batch):
        dx.get_frame(x[i], ax=axs[i])
        axs[i].get_xaxis().set_visible(False)
        axs[i].get_yaxis().set_visible(False)
    fig.tight_layout()
    fig.savefig(os.path.join(t_dir, '{:03d}.png'.format(t)))
    plt.close(fig)

datestamp = strftime("%Y-%m-%d_%H%M%S", gmtime())
#vid_fname = 'skidsteer-{}.mp4'.format(mode)
vid_fname = 'skidsteer-{}-{}.mp4'.format(mode, datestamp)

if os.path.exists(vid_fname):
    os.remove(vid_fname)
    
cmd = 'ffmpeg -r 16 -f image2 -i {}/%03d.png -vcodec libx264 -crf 25  -pix_fmt yuv420p {}'.format(
    t_dir, vid_fname
)
os.system(cmd)
print('Saving video to: {}'.format(vid_fname))

video = io.open(vid_fname, 'r+b').read()
encoded = base64.b64encode(video)
HTML(data='''<video alt="test" controls>
                <source src="data:video/mp4;base64,{0}" type="video/mp4" />
             </video>'''.format(encoded.decode('ascii')))
print("Cost vector: <cx, cy, cth> = <%.3f, %.3f, %.3f>" 
      % (goal_weights[0], goal_weights[1], goal_weights[2]))
print("Cumulative cost of %.2f" % cum_cost)

