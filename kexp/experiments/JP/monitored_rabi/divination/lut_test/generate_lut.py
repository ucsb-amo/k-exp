import numpy as np
from artiq.language import kernel, TArray, TFloat

### Parameters

I = np.eye(3, dtype=np.float64)

MHz=1e6
KHz=1e3

us=1e-6
ms=1e-3

omega_0=2*np.pi*147*MHz    #true gap
Omega=2*np.pi*85*KHz       # Rabi rate

offset=8                    # detuning of the set value of the drive frequency

m=11                  # discretization of the omega axis

omega_ctrl0=omega_0+2*offset*Omega       
omega_0_list=np.linspace(omega_0-2*offset*Omega, omega_0+2*offset*Omega, m)

omega_ctrl=omega_ctrl0  #drive frequency
dt=2*us                  # pulse length
nu=4                       # number of weak measurement pulses per shot

P0=np.ones(m)     #Initial "null" hypothesis
P0=P0/np.sum(P0)

n_photons=20  #Photons per weak measurement

k_lut=2

###

# 3. Helper for safe 1D interpolation
@kernel(flags={"fast-math"})
def interp(val, v_min, v_max, y1, y2):
    if v_min == v_max:
        return y1
    return ((val - v_min) * y2 + (v_max - val) * y1) / (v_max - v_min)

def generate_posterior_real_3d(P0, Omega, omega_ctrl, dt, n, k, state_list, t):
        P1 = []
        state_list_new = []
        
        for j in range(m):
            omega = omega_0_list[j]
            delta_omega = omega_ctrl - omega
            
            # ---------------------------------------------------------
            # 1. Z-Rotation Matrix (R_Z)
            # In the Bloch sphere, angles are doubled (2 * phase)
            # ---------------------------------------------------------
            phase = dt * delta_omega
            alpha_Z = 2.0 * phase 
            cos_z = np.cos(alpha_Z)
            sin_z = np.sin(alpha_Z)
            
            R_Z = np.array([
                [ cos_z,  sin_z, 0.0],
                [-sin_z,  cos_z, 0.0],
                [   0.0,    0.0, 1.0]
            ], dtype=np.float64)
            
            # ---------------------------------------------------------
            # 2. H-Rotation Matrix (R_H)
            # ---------------------------------------------------------
            norm_H = np.sqrt(Omega**2 + delta_omega**2)
            
            if norm_H == 0.0:
                R_H = I
            else:
                # Rotation angle in the Bloch sphere is 2 * theta
                alpha_H = 2.0 * norm_H * dt
                cos_H = np.cos(alpha_H)
                sin_H = np.sin(alpha_H)
                
                # Components of the normalized rotation axis (unit vector u)
                u_x = (Omega * np.cos(omega * t)) / norm_H
                u_y = (Omega * np.sin(omega * t)) / norm_H
                u_z = delta_omega / norm_H
                
                # Cross-product matrix (K) for Rodrigues' formula
                K = np.array([
                    [ 0.0, -u_z,  u_y],
                    [ u_z,  0.0, -u_x],
                    [-u_y,  u_x,  0.0]
                ], dtype=np.float64)
                
                # Rodrigues' rotation formula: R = I + sin(a)K + (1-cos(a))K^2
                R_H = I + sin_H * K + (1.0 - cos_H) * (K @ K)
            
            # ---------------------------------------------------------
            # 3. Evolution and State Update
            # ---------------------------------------------------------
            R = R_Z @ R_H
            
            # Multiply the 3x3 real matrix by the 3x1 real state vector
            state1 = R @ state_list[j]
            state_list_new.append(state1)
            
            # 4. Extract Probability P1
            # In the Bloch sphere, Sz = 1 is |0>, Sz = -1 is |1>
            # Therefore, P1 = 0.5 * (1 - Sz)
            P1.append(0.5 * (1.0 - state1[2]))
            
        # ---------------------------------------------------------
        # 5. Bayesian Update (Vectorized over m)
        # ---------------------------------------------------------
        P1 = np.array(P1, dtype=np.float64)
        
        # Calculate unnormalized posterior
        P_post = P0 * (P1**k) * ((1.0 - P1)**(n - k))
        
        # Normalize
        P_post /= np.sum(P_post)
        
        # Statistics
        mn = np.sum(P_post * omega_0_list)
        std = np.sqrt(np.sum(P_post * (omega_0_list - mn)**2))
        
        return mn, std, P_post, state_list_new

def f_nu_layers2(v, ff):
    nu=len(v)
    omega_ctrl_set=omega_ctrl0
    state=np.array([0, 0, 1], dtype=float)
    state_list=[state]*m
    t=0
    P_out2=[]
    P_out2.append(P0)
    P_post=P0
    entropy2=[]
    mean2=[]
    std2=[]
    Omega_set=Omega
    dt_set=dt

    for l in range(nu):
        k =int(v[l]*n_photons)
        #k=v[l]
        mn, std, P_post, state_list=generate_posterior_real_3d(P_post, Omega_set, omega_ctrl_set, dt_set, n_photons, k, state_list, t)
        t=t+10*us
        if (l+1)%ff==0:
            omega_ctrl_set=mn
            Omega_set=std
            dt_set=2/Omega_set
    return mn, std

###

lut_x0=np.linspace(0, 1, k_lut+1)
lut_f1=np.zeros(k_lut+1)
lut_g1=np.zeros(k_lut+1)

for i_lut in range(k_lut+1):
    lut_f1[i_lut], lut_g1[i_lut]=f_nu_layers2([lut_x0[i_lut]], 1)




@kernel(flags={"fast-math"})
def f_lut_interpol(x_vec: TArray(TFloat, num_dims=1))-> float:
    x = x_vec[0]
    u = x * k_lut
    i0 = int(u)
    if i0 >= k_lut:
        i0 = k_lut - 1
        t = 1.0
    else:
        t = u - i0
    y0 = lut_f1[i0]
    y1 = lut_f1[i0 + 1]
    return y0 + t * (y1 - y0)



@kernel(flags={"fast-math"})
def g_lut_interpol(x_vec: TArray(TFloat, num_dims=1)):
    x = x_vec[0]
    u = x * k_lut
    i0 = int(u)
    if i0 >= k_lut:
        i0 = k_lut - 1
        t = 1.0
    else:
        t = u - i0
    y0 = lut_g1[i0]
    y1 = lut_g1[i0 + 1]
    return y0 + t * (y1 - y0)

###


lut_x0=np.linspace(0, 1, k_lut+1)
lut_x1=np.linspace(0, 1, k_lut+1)

lut_f2=np.zeros((k_lut+1, k_lut+1))
lut_g2=np.zeros((k_lut+1, k_lut+1))

for i_lut in range(k_lut+1):
    for j_lut in range(k_lut+1):
        lut_f2[i_lut, j_lut], lut_g2[i_lut, j_lut]=f_nu_layers2([lut_x0[i_lut], lut_x1[j_lut]], 1)

@kernel(flags={"fast-math"})
def f_lut_interpol_2d(x_vec: TArray(TFloat, num_dims=1)) -> float:
    x0, x1 = x_vec[0], x_vec[1]

    u0 = x0 * k_lut
    i0 = int(u0)
    if i0 >= k_lut:
        i0 = k_lut - 1
        t0 = 1.0
    else:
        t0 = u0 - i0

    u1 = x1 * k_lut
    i1 = int(u1)
    if i1 >= k_lut:
        i1 = k_lut - 1
        t1 = 1.0
    else:
        t1 = u1 - i1

    i0p = i0 + 1
    i1p = i1 + 1

    c00 = lut_f2[i0, i1]
    c10 = lut_f2[i0p, i1]
    c01 = lut_f2[i0, i1p]
    c11 = lut_f2[i0p, i1p]

    a0 = c00 + t0 * (c10 - c00)
    a1 = c01 + t0 * (c11 - c01)
    return a0 + t1 * (a1 - a0)

@kernel(flags={"fast-math"})
def g_lut_interpol_2d(x_vec: TArray(TFloat, num_dims=1)):
    x0, x1 = x_vec[0], x_vec[1]

    u0 = x0 * k_lut
    i0 = int(u0)
    if i0 >= k_lut:
        i0 = k_lut - 1
        t0 = 1.0
    else:
        t0 = u0 - i0

    u1 = x1 * k_lut
    i1 = int(u1)
    if i1 >= k_lut:
        i1 = k_lut - 1
        t1 = 1.0
    else:
        t1 = u1 - i1

    i0p = i0 + 1
    i1p = i1 + 1

    c00 = lut_g2[i0, i1]
    c10 = lut_g2[i0p, i1]
    c01 = lut_g2[i0, i1p]
    c11 = lut_g2[i0p, i1p]

    a0 = c00 + t0 * (c10 - c00)
    a1 = c01 + t0 * (c11 - c01)
    return a0 + t1 * (a1 - a0)

###

lut_x0=np.linspace(0, 1, k_lut+1)
lut_x1=np.linspace(0, 1, k_lut+1)
lut_x2=np.linspace(0, 1, k_lut+1)

lut_f3=np.zeros((k_lut+1, k_lut+1, k_lut+1))
lut_g3=np.zeros((k_lut+1, k_lut+1, k_lut+1))
for i_lut in range(k_lut+1):
    for j_lut in range(k_lut+1):
        for l_lut in range(k_lut+1):
            lut_f3[i_lut, j_lut, l_lut], lut_g3[i_lut, j_lut, l_lut]=f_nu_layers2([lut_x0[i_lut], lut_x1[j_lut], lut_x2[l_lut]], 1)

@kernel(flags={"fast-math"})
def f_lut_interpol_3d(x_vec: TArray(TFloat, num_dims=1)):
    x0, x1, x2 = x_vec[0], x_vec[1], x_vec[2]

    u0 = x0 * k_lut
    i0 = int(u0)
    if i0 >= k_lut:
        i0 = k_lut - 1
        t0 = 1.0
    else:
        t0 = u0 - i0

    u1 = x1 * k_lut
    i1 = int(u1)
    if i1 >= k_lut:
        i1 = k_lut - 1
        t1 = 1.0
    else:
        t1 = u1 - i1

    u2 = x2 * k_lut
    i2 = int(u2)
    if i2 >= k_lut:
        i2 = k_lut - 1
        t2 = 1.0
    else:
        t2 = u2 - i2

    i0p = i0 + 1
    i1p = i1 + 1
    i2p = i2 + 1

    c000 = lut_f3[i0, i1, i2]
    c100 = lut_f3[i0p, i1, i2]
    c010 = lut_f3[i0, i1p, i2]
    c110 = lut_f3[i0p, i1p, i2]
    c001 = lut_f3[i0, i1, i2p]
    c101 = lut_f3[i0p, i1, i2p]
    c011 = lut_f3[i0, i1p, i2p]
    c111 = lut_f3[i0p, i1p, i2p]

    c00 = c000 + t0 * (c100 - c000)
    c10 = c010 + t0 * (c110 - c010)
    c01 = c001 + t0 * (c101 - c001)
    c11 = c011 + t0 * (c111 - c011)

    c0 = c00 + t1 * (c10 - c00)
    c1 = c01 + t1 * (c11 - c01)
    return c0 + t2 * (c1 - c0)

@kernel(flags={"fast-math"})
def g_lut_interpol_3d(x_vec: TArray(TFloat, num_dims=1)):
    x0, x1, x2 = x_vec[0], x_vec[1], x_vec[2]

    u0 = x0 * k_lut
    i0 = int(u0)
    if i0 >= k_lut:
        i0 = k_lut - 1
        t0 = 1.0
    else:
        t0 = u0 - i0

    u1 = x1 * k_lut
    i1 = int(u1)
    if i1 >= k_lut:
        i1 = k_lut - 1
        t1 = 1.0
    else:
        t1 = u1 - i1

    u2 = x2 * k_lut
    i2 = int(u2)
    if i2 >= k_lut:
        i2 = k_lut - 1
        t2 = 1.0
    else:
        t2 = u2 - i2

    i0p = i0 + 1
    i1p = i1 + 1
    i2p = i2 + 1

    c000 = lut_g3[i0, i1, i2]
    c100 = lut_g3[i0p, i1, i2]
    c010 = lut_g3[i0, i1p, i2]
    c110 = lut_g3[i0p, i1p, i2]
    c001 = lut_g3[i0, i1, i2p]
    c101 = lut_g3[i0p, i1, i2p]
    c011 = lut_g3[i0, i1p, i2p]
    c111 = lut_g3[i0p, i1p, i2p]

    c00 = c000 + t0 * (c100 - c000)
    c10 = c010 + t0 * (c110 - c010)
    c01 = c001 + t0 * (c101 - c001)
    c11 = c011 + t0 * (c111 - c011)

    c0 = c00 + t1 * (c10 - c00)
    c1 = c01 + t1 * (c11 - c01)
    return c0 + t2 * (c1 - c0)

###

lut_x0 = np.linspace(0, 1, k_lut+1)
lut_x1 = np.linspace(0, 1, k_lut+1)
lut_x2 = np.linspace(0, 1, k_lut+1)
lut_x3 = np.linspace(0, 1, k_lut+1)

lut_f4 = np.zeros((k_lut+1, k_lut+1, k_lut+1, k_lut+1))
lut_g4 = np.zeros((k_lut+1, k_lut+1, k_lut+1, k_lut+1))

for i_lut in range(k_lut+1):
    for j_lut in range(k_lut+1):
        for l_lut in range(k_lut+1):
            for m_lut in range(k_lut+1):
                lut_f4[i_lut, j_lut, l_lut, m_lut], lut_g4[i_lut, j_lut, l_lut, m_lut] = f_nu_layers2(
                    [lut_x0[i_lut], lut_x1[j_lut], lut_x2[l_lut], lut_x3[m_lut]], 1
                )

@kernel(flags={"fast-math"})
def f_lut_interpol_4d(x_vec: TArray(TFloat, num_dims=1)):
    x0, x1, x2, x3 = x_vec[0], x_vec[1], x_vec[2], x_vec[3]

    u0 = x0 * k_lut
    i0 = int(u0)
    if i0 >= k_lut:
        i0 = k_lut - 1
        t0 = 1.0
    else:
        t0 = u0 - i0

    u1 = x1 * k_lut
    i1 = int(u1)
    if i1 >= k_lut:
        i1 = k_lut - 1
        t1 = 1.0
    else:
        t1 = u1 - i1

    u2 = x2 * k_lut
    i2 = int(u2)
    if i2 >= k_lut:
        i2 = k_lut - 1
        t2 = 1.0
    else:
        t2 = u2 - i2

    u3 = x3 * k_lut
    i3 = int(u3)
    if i3 >= k_lut:
        i3 = k_lut - 1
        t3 = 1.0
    else:
        t3 = u3 - i3

    i0p = i0 + 1
    i1p = i1 + 1
    i2p = i2 + 1
    i3p = i3 + 1

    c0000 = lut_f4[i0, i1, i2, i3]
    c1000 = lut_f4[i0p, i1, i2, i3]
    c0100 = lut_f4[i0, i1p, i2, i3]
    c1100 = lut_f4[i0p, i1p, i2, i3]
    c0010 = lut_f4[i0, i1, i2p, i3]
    c1010 = lut_f4[i0p, i1, i2p, i3]
    c0110 = lut_f4[i0, i1p, i2p, i3]
    c1110 = lut_f4[i0p, i1p, i2p, i3]
    c0001 = lut_f4[i0, i1, i2, i3p]
    c1001 = lut_f4[i0p, i1, i2, i3p]
    c0101 = lut_f4[i0, i1p, i2, i3p]
    c1101 = lut_f4[i0p, i1p, i2, i3p]
    c0011 = lut_f4[i0, i1, i2p, i3p]
    c1011 = lut_f4[i0p, i1, i2p, i3p]
    c0111 = lut_f4[i0, i1p, i2p, i3p]
    c1111 = lut_f4[i0p, i1p, i2p, i3p]

    d000 = c0000 + t0 * (c1000 - c0000)
    d100 = c0100 + t0 * (c1100 - c0100)
    d010 = c0010 + t0 * (c1010 - c0010)
    d110 = c0110 + t0 * (c1110 - c0110)
    d001 = c0001 + t0 * (c1001 - c0001)
    d101 = c0101 + t0 * (c1101 - c0101)
    d011 = c0011 + t0 * (c1011 - c0011)
    d111 = c0111 + t0 * (c1111 - c0111)

    e00 = d000 + t1 * (d100 - d000)
    e10 = d010 + t1 * (d110 - d010)
    e01 = d001 + t1 * (d101 - d001)
    e11 = d011 + t1 * (d111 - d011)

    f0 = e00 + t2 * (e10 - e00)
    f1 = e01 + t2 * (e11 - e01)
    return f0 + t3 * (f1 - f0)

@kernel(flags={"fast-math"})
def g_lut_interpol_4d(x_vec: TArray(TFloat, num_dims=1)):
    x0, x1, x2, x3 = x_vec[0], x_vec[1], x_vec[2], x_vec[3]

    u0 = x0 * k_lut
    i0 = int(u0)
    if i0 >= k_lut:
        i0 = k_lut - 1
        t0 = 1.0
    else:
        t0 = u0 - i0

    u1 = x1 * k_lut
    i1 = int(u1)
    if i1 >= k_lut:
        i1 = k_lut - 1
        t1 = 1.0
    else:
        t1 = u1 - i1

    u2 = x2 * k_lut
    i2 = int(u2)
    if i2 >= k_lut:
        i2 = k_lut - 1
        t2 = 1.0
    else:
        t2 = u2 - i2

    u3 = x3 * k_lut
    i3 = int(u3)
    if i3 >= k_lut:
        i3 = k_lut - 1
        t3 = 1.0
    else:
        t3 = u3 - i3

    i0p = i0 + 1
    i1p = i1 + 1
    i2p = i2 + 1
    i3p = i3 + 1

    c0000 = lut_g4[i0, i1, i2, i3]
    c1000 = lut_g4[i0p, i1, i2, i3]
    c0100 = lut_g4[i0, i1p, i2, i3]
    c1100 = lut_g4[i0p, i1p, i2, i3]
    c0010 = lut_g4[i0, i1, i2p, i3]
    c1010 = lut_g4[i0p, i1, i2p, i3]
    c0110 = lut_g4[i0, i1p, i2p, i3]
    c1110 = lut_g4[i0p, i1p, i2p, i3]
    c0001 = lut_g4[i0, i1, i2, i3p]
    c1001 = lut_g4[i0p, i1, i2, i3p]
    c0101 = lut_g4[i0, i1p, i2, i3p]
    c1101 = lut_g4[i0p, i1p, i2, i3p]
    c0011 = lut_g4[i0, i1, i2p, i3p]
    c1011 = lut_g4[i0p, i1, i2p, i3p]
    c0111 = lut_g4[i0, i1p, i2p, i3p]
    c1111 = lut_g4[i0p, i1p, i2p, i3p]

    d000 = c0000 + t0 * (c1000 - c0000)
    d100 = c0100 + t0 * (c1100 - c0100)
    d010 = c0010 + t0 * (c1010 - c0010)
    d110 = c0110 + t0 * (c1110 - c0110)
    d001 = c0001 + t0 * (c1001 - c0001)
    d101 = c0101 + t0 * (c1101 - c0101)
    d011 = c0011 + t0 * (c1011 - c0011)
    d111 = c0111 + t0 * (c1111 - c0111)

    e00 = d000 + t1 * (d100 - d000)
    e10 = d010 + t1 * (d110 - d010)
    e01 = d001 + t1 * (d101 - d001)
    e11 = d011 + t1 * (d111 - d011)

    f0 = e00 + t2 * (e10 - e00)
    f1 = e01 + t2 * (e11 - e01)
    return f0 + t3 * (f1 - f0)

mean_func_list = [f_lut_interpol, f_lut_interpol_2d, f_lut_interpol_3d]
std_func_list = [g_lut_interpol, g_lut_interpol_2d, g_lut_interpol_3d]  