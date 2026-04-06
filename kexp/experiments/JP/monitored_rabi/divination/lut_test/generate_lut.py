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
nu=4                        # number of weak measurement pulses per shot

P0=np.ones(m)     #Initial "null" hypothesis
P0=P0/np.sum(P0)

n_photons=20  #Photons per weak measurement

k_lut=2

###

# 3. Helper for safe 1D interpolation
@kernel
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




@kernel
def f_lut_interpol(x_vec: TArray(TFloat, num_dims=1))-> float:
    #x=0.0
    x=x_vec[0]
    
    
    imin = int(np.floor(k_lut * x))
    imax = int(np.ceil(k_lut * x))
    
    # Prevent division by zero: if x is exactly on a grid point, 
    # just return the known value.
    if imin == imax:
        return lut_f1[imin]
        
    y1 = lut_f1[imin]
    y2 = lut_f1[imax]
    ym = ((x - lut_x0[imin]) * y2 + (lut_x0[imax] - x) * y1) / (lut_x0[imax] - lut_x0[imin])
    
    return ym



@kernel
def g_lut_interpol(x_vec: TArray(TFloat, num_dims=1)):

    x=x_vec[0]

    ym=0.0
    imin = int(np.floor(k_lut * x))
    imax = int(np.ceil(k_lut * x))
    
    # Prevent division by zero: if x is exactly on a grid point, 
    # just return the known value.
    if imin == imax:
        return lut_g1[imin]
        
    y1 = lut_g1[imin]
    y2 = lut_g1[imax]
    ym = ((x - lut_x0[imin]) * y2 + (lut_x0[imax] - x) * y1) / (lut_x0[imax] - lut_x0[imin])
    
    return ym

###


lut_x0=np.linspace(0, 1, k_lut+1)
lut_x1=np.linspace(0, 1, k_lut+1)

lut_f2=np.zeros((k_lut+1, k_lut+1))
lut_g2=np.zeros((k_lut+1, k_lut+1))

for i_lut in range(k_lut+1):
    for j_lut in range(k_lut+1):
        lut_f2[i_lut, j_lut], lut_g2[i_lut, j_lut]=f_nu_layers2([lut_x0[i_lut], lut_x1[j_lut]], 1)

@kernel
def f_lut_interpol_2d(x_vec: TArray(TFloat, num_dims=1)) -> float:

    
    # x is now a 2-element array/list: [x0, x1]
    x0, x1 = x_vec[0], x_vec[1]

    
    # 1. Find bounding indices for the first dimension (x0)
    i0_min = int(np.floor(k_lut * x0))
    i0_max = int(np.ceil(k_lut * x0))
    
    # 2. Find bounding indices for the second dimension (x1)
    i1_min = int(np.floor(k_lut * x1))
    i1_max = int(np.ceil(k_lut * x1))
    
    # Retrieve grid coordinate values (assuming 1D arrays lut_x0 and lut_x1 exist)
    x0_min, x0_max = lut_x0[i0_min], lut_x0[i0_max]
    x1_min, x1_max = lut_x1[i1_min], lut_x1[i1_max]
    
    # 3. Retrieve the 4 corner values from the 2D LUT
    # Q11 (bottom-left), Q21 (bottom-right), Q12 (top-left), Q22 (top-right)
    Q11 = lut_f2[i0_min, i1_min]
    Q21 = lut_f2[i0_max, i1_min]
    Q12 = lut_f2[i0_min, i1_max]
    Q22 = lut_f2[i0_max, i1_max]
    
    # Distances for denominators (with guards against division by zero)
    dx0 = (x0_max - x0_min) if x0_max != x0_min else 1.0
    dx1 = (x1_max - x1_min) if x1_max != x1_min else 1.0
    
    # 4. Interpolate along x0 at the bottom edge (i1_min) and top edge (i1_max)
    if x0_max == x0_min:
        f_bottom = Q11
        f_top = Q12
    else:
        f_bottom = ((x0 - x0_min) * Q21 + (x0_max - x0) * Q11) / dx0
        f_top    = ((x0 - x0_min) * Q22 + (x0_max - x0) * Q12) / dx0
        
    # 5. Interpolate along x1 using the two intermediate results
    if x1_max == x1_min:
        ym = f_bottom
    else:
        ym = ((x1 - x1_min) * f_top + (x1_max - x1) * f_bottom) / dx1
        
    return ym

@kernel
def g_lut_interpol_2d(x_vec: TArray(TFloat, num_dims=1)):
    # x is now a 2-element array/list: [x0, x1]
    x0, x1 = x_vec[0], x_vec[1]

    
    # 1. Find bounding indices for the first dimension (x0)
    i0_min = int(np.floor(k_lut * x0))
    i0_max = int(np.ceil(k_lut * x0))
    
    # 2. Find bounding indices for the second dimension (x1)
    i1_min = int(np.floor(k_lut * x1))
    i1_max = int(np.ceil(k_lut * x1))
    
    # Retrieve grid coordinate values (assuming 1D arrays lut_x0 and lut_x1 exist)
    x0_min, x0_max = lut_x0[i0_min], lut_x0[i0_max]
    x1_min, x1_max = lut_x1[i1_min], lut_x1[i1_max]
    
    # 3. Retrieve the 4 corner values from the 2D LUT
    # Q11 (bottom-left), Q21 (bottom-right), Q12 (top-left), Q22 (top-right)
    Q11 = lut_g2[i0_min, i1_min]
    Q21 = lut_g2[i0_max, i1_min]
    Q12 = lut_g2[i0_min, i1_max]
    Q22 = lut_g2[i0_max, i1_max]
    
    # Distances for denominators (with guards against division by zero)
    dx0 = (x0_max - x0_min) if x0_max != x0_min else 1.0
    dx1 = (x1_max - x1_min) if x1_max != x1_min else 1.0
    
    # 4. Interpolate along x0 at the bottom edge (i1_min) and top edge (i1_max)
    if x0_max == x0_min:
        f_bottom = Q11
        f_top = Q12
    else:
        f_bottom = ((x0 - x0_min) * Q21 + (x0_max - x0) * Q11) / dx0
        f_top    = ((x0 - x0_min) * Q22 + (x0_max - x0) * Q12) / dx0
        
    # 5. Interpolate along x1 using the two intermediate results
    if x1_max == x1_min:
        ym = f_bottom
    else:
        ym = ((x1 - x1_min) * f_top + (x1_max - x1) * f_bottom) / dx1
        
    return ym

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

@kernel
def f_lut_interpol_3d(x_vec: TArray(TFloat, num_dims=1)):
    # x is a 3-element array/list: [x0, x1, x2]
    x0, x1, x2 = x_vec[0], x_vec[1], x_vec[2]
    
    # 1. Bounding indices for each dimension
    i0_min = int(np.floor(k_lut * x0))
    i0_max = int(np.ceil(k_lut * x0))
    
    i1_min = int(np.floor(k_lut * x1))
    i1_max = int(np.ceil(k_lut * x1))
    
    i2_min = int(np.floor(k_lut * x2))
    i2_max = int(np.ceil(k_lut * x2))
    
    # Grid coordinates
    x0_min, x0_max = lut_x0[i0_min], lut_x0[i0_max]
    x1_min, x1_max = lut_x1[i1_min], lut_x1[i1_max]
    x2_min, x2_max = lut_x2[i2_min], lut_x2[i2_max]
    
    # 2. Fetch the 8 corners of the 3D cube from the LUT
    c000 = lut_f3[i0_min, i1_min, i2_min]
    c100 = lut_f3[i0_max, i1_min, i2_min]
    c010 = lut_f3[i0_min, i1_max, i2_min]
    c110 = lut_f3[i0_max, i1_max, i2_min]
    c001 = lut_f3[i0_min, i1_min, i2_max]
    c101 = lut_f3[i0_max, i1_min, i2_max]
    c011 = lut_f3[i0_min, i1_max, i2_max]
    c111 = lut_f3[i0_max, i1_max, i2_max]
        
    # 4. Interpolate along x0 (reduces 8 points to 4)
    c00 = interp(x0, x0_min, x0_max, c000, c100)
    c10 = interp(x0, x0_min, x0_max, c010, c110)
    c01 = interp(x0, x0_min, x0_max, c001, c101)
    c11 = interp(x0, x0_min, x0_max, c011, c111)
    
    # 5. Interpolate along x1 (reduces 4 points to 2)
    c0 = interp(x1, x1_min, x1_max, c00, c10)
    c1 = interp(x1, x1_min, x1_max, c01, c11)
    
    # 6. Interpolate along x2 (reduces 2 points to 1 final value)
    ym = interp(x2, x2_min, x2_max, c0, c1)
    
    return ym

@kernel
def g_lut_interpol_3d(x_vec: TArray(TFloat, num_dims=1)):
    # x is a 3-element array/list: [x0, x1, x2]
    ym=0.0
    x0, x1, x2 = x_vec[0], x_vec[1], x_vec[2]
    
    # 1. Bounding indices for each dimension
    i0_min = int(np.floor(k_lut * x0))
    i0_max = int(np.ceil(k_lut * x0))
    
    i1_min = int(np.floor(k_lut * x1))
    i1_max = int(np.ceil(k_lut * x1))
    
    i2_min = int(np.floor(k_lut * x2))
    i2_max = int(np.ceil(k_lut * x2))
    
    # Grid coordinates
    x0_min, x0_max = lut_x0[i0_min], lut_x0[i0_max]
    x1_min, x1_max = lut_x1[i1_min], lut_x1[i1_max]
    x2_min, x2_max = lut_x2[i2_min], lut_x2[i2_max]
    
    # 2. Fetch the 8 corners of the 3D cube from the LUT
    c000 = lut_g3[i0_min, i1_min, i2_min]
    c100 = lut_g3[i0_max, i1_min, i2_min]
    c010 = lut_g3[i0_min, i1_max, i2_min]
    c110 = lut_g3[i0_max, i1_max, i2_min]
    c001 = lut_g3[i0_min, i1_min, i2_max]
    c101 = lut_g3[i0_max, i1_min, i2_max]
    c011 = lut_g3[i0_min, i1_max, i2_max]
    c111 = lut_g3[i0_max, i1_max, i2_max]
        
    # 4. Interpolate along x0 (reduces 8 points to 4)
    c00 = interp(x0, x0_min, x0_max, c000, c100)
    c10 = interp(x0, x0_min, x0_max, c010, c110)
    c01 = interp(x0, x0_min, x0_max, c001, c101)
    c11 = interp(x0, x0_min, x0_max, c011, c111)
    
    # 5. Interpolate along x1 (reduces 4 points to 2)
    c0 = interp(x1, x1_min, x1_max, c00, c10)
    c1 = interp(x1, x1_min, x1_max, c01, c11)
    
    # 6. Interpolate along x2 (reduces 2 points to 1 final value)
    ym = interp(x2, x2_min, x2_max, c0, c1)
    
    return ym

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

@kernel
def f_lut_interpol_4d(x_vec: TArray(TFloat, num_dims=1)):
    # x is a 4-element array/list: [x0, x1, x2, x3]
    x0, x1, x2, x3 = x_vec[0], x_vec[1], x_vec[2], x_vec[3]
    
    # # 1. Bounding indices for each dimension using k_lut
    i0_min = int(np.floor(k_lut * x0))
    i0_max = int(np.ceil(k_lut * x0))
    
    i1_min = int(np.floor(k_lut * x1))
    i1_max = int(np.ceil(k_lut * x1))
    
    i2_min = int(np.floor(k_lut * x2))
    i2_max = int(np.ceil(k_lut * x2))
    
    i3_min = int(np.floor(k_lut * x3))
    i3_max = int(np.ceil(k_lut * x3))
    
    # # Grid coordinates
    x0_min, x0_max = lut_x0[i0_min], lut_x0[i0_max]
    x1_min, x1_max = lut_x1[i1_min], lut_x1[i1_max]
    x2_min, x2_max = lut_x2[i2_min], lut_x2[i2_max]
    x3_min, x3_max = lut_x3[i3_min], lut_x3[i3_max]
    
    # 2. 4D multilinear interpolation using nested loops over corner bits.
    idx0 = [i0_min, i0_max]
    idx1 = [i1_min, i1_max]
    idx2 = [i2_min, i2_max]
    idx3 = [i3_min, i3_max]

    if x0_max == x0_min:
        w0 = [1.0, 0.0]
    else:
        w0 = [(x0_max - x0) / (x0_max - x0_min), (x0 - x0_min) / (x0_max - x0_min)]

    if x1_max == x1_min:
        w1 = [1.0, 0.0]
    else:
        w1 = [(x1_max - x1) / (x1_max - x1_min), (x1 - x1_min) / (x1_max - x1_min)]

    if x2_max == x2_min:
        w2 = [1.0, 0.0]
    else:
        w2 = [(x2_max - x2) / (x2_max - x2_min), (x2 - x2_min) / (x2_max - x2_min)]

    if x3_max == x3_min:
        w3 = [1.0, 0.0]
    else:
        w3 = [(x3_max - x3) / (x3_max - x3_min), (x3 - x3_min) / (x3_max - x3_min)]

    ym = 0.0
    for b0 in range(2):
        for b1 in range(2):
            for b2 in range(2):
                for b3 in range(2):
                    ym += (
                        w0[b0]
                        * w1[b1]
                        * w2[b2]
                        * w3[b3]
                        * lut_f4[idx0[b0], idx1[b1], idx2[b2], idx3[b3]]
                    )

    return ym

@kernel
def g_lut_interpol_4d(x_vec: TArray(TFloat, num_dims=1)):
    # x is a 4-element array/list: [x0, x1, x2, x3]
    x0, x1, x2, x3 = x_vec[0], x_vec[1], x_vec[2], x_vec[3]
    
    # 1. Bounding indices for each dimension using k_lut
    i0_min = int(np.floor(k_lut * x0))
    i0_max = int(np.ceil(k_lut * x0))
    
    i1_min = int(np.floor(k_lut * x1))
    i1_max = int(np.ceil(k_lut * x1))
    
    i2_min = int(np.floor(k_lut * x2))
    i2_max = int(np.ceil(k_lut * x2))
    
    i3_min = int(np.floor(k_lut * x3))
    i3_max = int(np.ceil(k_lut * x3))
    
    # Grid coordinates
    x0_min, x0_max = lut_x0[i0_min], lut_x0[i0_max]
    x1_min, x1_max = lut_x1[i1_min], lut_x1[i1_max]
    x2_min, x2_max = lut_x2[i2_min], lut_x2[i2_max]
    x3_min, x3_max = lut_x3[i3_min], lut_x3[i3_max]
    
    # 2. 4D multilinear interpolation using nested loops over corner bits.
    idx0 = [i0_min, i0_max]
    idx1 = [i1_min, i1_max]
    idx2 = [i2_min, i2_max]
    idx3 = [i3_min, i3_max]

    if x0_max == x0_min:
        w0 = [1.0, 0.0]
    else:
        w0 = [(x0_max - x0) / (x0_max - x0_min), (x0 - x0_min) / (x0_max - x0_min)]

    if x1_max == x1_min:
        w1 = [1.0, 0.0]
    else:
        w1 = [(x1_max - x1) / (x1_max - x1_min), (x1 - x1_min) / (x1_max - x1_min)]

    if x2_max == x2_min:
        w2 = [1.0, 0.0]
    else:
        w2 = [(x2_max - x2) / (x2_max - x2_min), (x2 - x2_min) / (x2_max - x2_min)]

    if x3_max == x3_min:
        w3 = [1.0, 0.0]
    else:
        w3 = [(x3_max - x3) / (x3_max - x3_min), (x3 - x3_min) / (x3_max - x3_min)]

    ym = 0.0
    for b0 in range(2):
        for b1 in range(2):
            for b2 in range(2):
                for b3 in range(2):
                    ym += (
                        w0[b0]
                        * w1[b1]
                        * w2[b2]
                        * w3[b3]
                        * lut_g4[idx0[b0], idx1[b1], idx2[b2], idx3[b3]]
                    )
    
    return ym

mean_func_list=[f_lut_interpol, f_lut_interpol_2d, f_lut_interpol_3d, f_lut_interpol_4d]
std_func_list=[g_lut_interpol, g_lut_interpol_2d, g_lut_interpol_3d, g_lut_interpol_4d]