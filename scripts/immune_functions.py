import numpy as np 
import matplotlib.pyplot as plt
import cvxpy as cvx
from scipy.linalg import circulant
from scipy.stats import norm
import seaborn as sns
import pandas as pd
from scipy.integrate import solve_ivp
from scipy.spatial.distance import cdist

def BinaryRandomMatrix(S,M,p):
    r = np.random.rand(S,M)
    m = np.zeros((S,M))
    m[r<p] = 1.0
    return m

def MakeAffinities(params):
    sampling = params['sampling']
    if sampling == 'Binary':
        pix = BinaryRandomMatrix(params['Num_tcell'],params['Num_sites'],params['pval_cell']) 
        palphax = (params['c'] + np.random.normal(0,params['sigma_cp'],(params['Num_treg'],params['Num_sites']) ) )* BinaryRandomMatrix(params['Num_treg'],params['Num_sites'],params['pval_treg']) 
    elif sampling == '1D':
        circ = circulant(norm.pdf(np.linspace(-params['Num_sites']/2,params['Num_sites']/2,params['Num_sites'])/params['niche_width'])/norm.pdf(0))
        Tcell_choice = np.random.choice(params['Num_sites'],size=params['Num_tcell'],replace=True)
        Treg_choice = np.random.choice(params['Num_sites'],size=params['Num_treg'],replace=True)
        pix = circ[Tcell_choice,:]
        palphax = params['c']*circ[Treg_choice,:]
    elif sampling == 'Multidimensional':
        antigens = np.random.randn(params['Num_sites'],params['shape_dim'])
        receptors = np.random.randn(params['Num_tcell'],params['shape_dim'])
        receptors_reg = np.random.randn(params['Num_treg'],params['shape_dim'])
        pix = np.exp(-cdist(receptors,antigens,'sqeuclidean')/(2*params['sigma']**2))
        palphax = params['c']*np.exp(-cdist(receptors_reg,antigens,'sqeuclidean')/(2*params['sigma']**2))
    elif sampling == 'Circulant':
        circ = circulant(norm.pdf(np.linspace(-params['Num_sites']/2,params['Num_sites']/2,params['Num_sites'])/params['niche_width']))
        pix = circ[np.linspace(0,params['Num_sites']-1,params['Num_tcell'],dtype=int),:]
        palphax = params['c']*circ[np.linspace(0,params['Num_sites']-1,params['Num_treg'],dtype=int),:]
    elif sampling == 'Fixed_degree':
        pix = BinaryRandomMatrix(params['Num_tcell'],params['Num_sites'],params['pval_cell']) 
        palphax = np.zeros((params['Num_treg'],params['Num_sites']))
        degree = np.asarray(params['degree']+np.random.randn(params['Num_sites'])*params['sigma_degree'],dtype=int)
        for i in range(params['Num_sites']):
            palphax[:degree[i],i] = params['c']*np.ones(degree[i])+np.random.randn(degree[i])*params['sigma_c']
            np.random.shuffle(palphax[:,i])
    else:
        print('Invalid sampling choice. Valid choices are Binary, 1D, Circulant or Fixed_degree.')
        pix = np.nan
        palphax = np.nan
    return pix, palphax

def MakeOverlaps(pix,palphax,vx):
    phi_reg_reg = (palphax*vx).dot(palphax.T)
    phi_cell_reg = (pix*vx).dot(palphax.T)
    rvals = pix.dot(vx)
    return phi_reg_reg, phi_cell_reg, rvals

def TrainNetwork(phi_reg_reg,phi_cell_reg,rvals):
    Num_treg = len(phi_reg_reg)
    Num_tcell = len(phi_cell_reg)
    Treg = cvx.Variable(Num_treg)
    G = np.vstack((-(phi_cell_reg.T/rvals).T,-np.eye(Num_treg)))
    h = np.hstack((-np.ones(Num_tcell),np.zeros(Num_treg)))
    constraints = [G@Treg <= h]
    obj = cvx.Minimize((1/2)*cvx.quad_form(Treg,phi_reg_reg))
    prob = cvx.Problem(obj, constraints)
    prob.solve(solver=cvx.ECOS,abstol=1e-7,feastol=1e-7,abstol_inacc=1e-7,feastol_inacc=1e-7,max_iters=100,verbose=False)
    Tcell=constraints[0].dual_value[:Num_tcell]/rvals
    Treg=Treg.value
    return Tcell,Treg

def ddt_simple(t,y,phi_reg_reg,phi_cell_reg,rvals):
    Num_treg = len(phi_reg_reg)
    Num_tcell = len(phi_cell_reg)
    Tcell = y[:Num_tcell]
    Treg = y[Num_tcell:]
    
    dTcelldt = Tcell*(rvals-phi_cell_reg.dot(Treg))
    dTregdt = Treg*(phi_cell_reg.T.dot(Tcell) - phi_reg_reg.dot(Treg))
    
    return np.hstack((dTcelldt, dTregdt))

def ddt_full(t,y,pix,palphax,vx):
    Num_treg = len(palphax)
    Num_tcell = len(pix)
    Tcell = y[:Num_tcell]
    Treg = y[Num_tcell:]

    Qx = palphax.T.dot(Treg)
    ILx = (pix.T.dot(Tcell))/(palphax.T.dot(Treg))
    
    dTcelldt = Tcell*pix.dot(vx*(1-Qx))
    dTregdt = Treg*palphax.dot(vx*(ILx-1))
    
    return np.hstack((dTcelldt, dTregdt))