# DFT + NIEL Pipeline Installation Guide (Ubuntu ARM64)

Complete installation instructions for running the DFT + NIEL pipeline for displacement damage calculations on Ubuntu ARM64 (aarch64). Includes Geant4 Monte Carlo for nuclear NIEL channels.

## Prerequisites

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y build-essential gfortran cmake git wget curl \
    libfftw3-dev libhdf5-dev libgmp-dev libboost-all-dev \
    libblas-dev liblapack-dev pkg-config
```

## 1. Install Miniconda (ARM64)

```bash
cd ~
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-aarch64.sh
bash Miniconda3-latest-Linux-aarch64.sh -b -p $HOME/miniconda3
rm Miniconda3-latest-Linux-aarch64.sh

# initialize conda
~/miniconda3/bin/conda init bash
source ~/.bashrc
```

## 2. Create Conda Environment

```bash
conda create -n DSI python=3.11 -y
conda activate DSI

# install python packages
conda install -c conda-forge numpy scipy pandas matplotlib seaborn jupyter ipykernel -y
conda install -c conda-forge ase jarvis-tools nglview -y
conda install -c conda-forge mpi4py openmpi openblas -y

# enable nglview in jupyter
jupyter nbextension enable --py nglview --sys-prefix
```

## 3. Install Quantum ESPRESSO

```bash
conda activate DSI
conda install -c conda-forge qe -y
```

Verify installation:
```bash
which pw.x
pw.x --version
```

## 4. Install Pseudopotentials

We use the **JTH PAW v2.0** pseudopotential library from ABINIT - a complete, uniform set of PAW pseudopotentials covering 86 elements. This avoids issues from mixing different pseudopotential types (PAW vs ultrasoft).

```bash
# create pseudo directory
sudo mkdir -p /usr/share/espresso/pseudo

# download the complete JTH PAW v2.0 library (GGA-PBE, UPF format)
cd /tmp
curl -L -o jth_paw.tar.gz "https://github.com/abinit/paw_jth_datasets/raw/main/pseudos/JTH-PBE-v2.0/JTH-v2.0-GGA-PBE-atomicdata-upf.tar.gz"

# extract and install
tar -xzf jth_paw.tar.gz
sudo cp JTH-v2.0-GGA-PBE-atomicdata-upf/*.UPF /usr/share/espresso/pseudo/

# cleanup
rm -rf jth_paw.tar.gz JTH-v2.0-GGA-PBE-atomicdata-upf

# verify installation
echo "Installed $(ls /usr/share/espresso/pseudo/*.UPF | wc -l) pseudopotentials"
echo "Covering $(ls /usr/share/espresso/pseudo/*.UPF | xargs -n1 basename | cut -d. -f1 | sort -u | wc -l) elements"
```

**Library details:**
- **Source:** ABINIT JTH PAW v2.0 (https://www.abinit.org/pseudopotential.html)
- **Type:** PAW (Projector Augmented Wave) - all files are consistent
- **Functional:** GGA-PBE
- **Format:** UPF (Quantum ESPRESSO compatible)
- **Coverage:** 86 elements (H to Rn, including lanthanides)
- **Naming:** `Element.GGA_PBE-JTH.UPF` (some elements have `_sp` semicore variants)

A symbolic link to the pseudopotentials is available at `pseudopotentials/` in this directory for easy browsing.

This library is well-tested and suitable for high-throughput calculations with any JARVIS material.

## 5. Install Geant4 (Monte Carlo NIEL)

Geant4 provides high-fidelity nuclear elastic and inelastic NIEL via the QGSP_BIC_HP physics list. No pre-built packages exist for ARM64, so we build from source.

### 5a. Install build tools

```bash
conda activate DSI
conda install -c conda-forge cxx-compiler cmake ninja -y
```

### 5b. Build Geant4 from source

```bash
cd ~
mkdir geant4-build && cd geant4-build

# download source
wget https://github.com/Geant4/geant4/archive/refs/tags/v11.3.2.tar.gz
tar -xzf v11.3.2.tar.gz

# configure (minimal build, no visualization)
mkdir build && cd build
cmake ../geant4-11.3.2 \
    -DCMAKE_INSTALL_PREFIX=$HOME/geant4-install \
    -DGEANT4_INSTALL_DATA=ON \
    -DGEANT4_USE_OPENGL_X11=OFF \
    -DGEANT4_USE_QT=OFF \
    -DGEANT4_USE_GDML=OFF \
    -DGEANT4_BUILD_MULTITHREADED=OFF \
    -DCMAKE_BUILD_TYPE=Release \
    -GNinja

# build and install (takes ~15 min)
ninja -j$(nproc)
ninja install
```

### 5c. Install Python bindings

```bash
conda activate DSI
export CMAKE_PREFIX_PATH=$HOME/geant4-install:$CMAKE_PREFIX_PATH
export Geant4_DIR=$HOME/geant4-install/lib/cmake/Geant4
pip install geant4-pybind
```

### 5d. Set environment variables

Add to `~/.bashrc`:
```bash
echo 'export GEANT4_DATA_DIR=$HOME/geant4-build/build/data' >> ~/.bashrc
echo 'export LD_LIBRARY_PATH=$HOME/geant4-install/lib:$LD_LIBRARY_PATH' >> ~/.bashrc
source ~/.bashrc
```

### 5e. Verify

```bash
conda activate DSI
python -c "
import os
os.environ['GEANT4_DATA_DIR'] = os.path.expanduser('~/geant4-build/build/data')
import geant4_pybind as g4
print(f'geant4 loaded: {g4.G4Version}')
"
```

## 6. Register Jupyter Kernel

```bash
conda activate DSI
python -m ipykernel install --user --name DSI --display-name "DSI"
```

## 7. Environment Variables

Add to `~/.bashrc` (skip lines already added in step 5d):
```bash
echo 'export LD_LIBRARY_PATH=$HOME/miniconda3/envs/DSI/lib:$LD_LIBRARY_PATH' >> ~/.bashrc
source ~/.bashrc
```

## Verification

Run this script to verify all components:

```bash
conda activate DSI

echo "--- checking executables ---"
for exe in pw.x mpirun; do
    if which $exe > /dev/null 2>&1; then
        echo "OK: $exe -> $(which $exe)"
    else
        echo "MISSING: $exe"
    fi
done

echo ""
echo "--- checking python packages ---"
python << 'EOF'
import os
for pkg in ['numpy', 'ase', 'jarvis', 'nglview', 'pandas']:
    try:
        mod = __import__(pkg)
        ver = getattr(mod, '__version__', 'OK')
        print(f"OK: {pkg} {ver}")
    except ImportError:
        print(f"MISSING: {pkg}")

# geant4
try:
    os.environ['GEANT4_DATA_DIR'] = os.path.expanduser('~/geant4-build/build/data')
    import geant4_pybind as g4
    print(f"OK: geant4-pybind ({g4.G4Version})")
except ImportError:
    print("MISSING: geant4-pybind (optional, needed for Geant4_NIEL.ipynb)")
EOF

echo ""
echo "--- checking pseudopotentials ---"
count=$(ls /usr/share/espresso/pseudo/*.UPF /usr/share/espresso/pseudo/*.upf 2>/dev/null | wc -l)
echo "pseudopotential files: $count"
```

## Running the Notebooks

```bash
conda activate DSI
cd /path/to/LUMENS-PV/calculating_energy_threshold_displacement

# analytical niel (dft + screened rutherford + compound nucleus model)
jupyter notebook DFT+NIEL.ipynb

# geant4 monte carlo niel (nuclear elastic + inelastic via QGSP_BIC_HP)
jupyter notebook Geant4_NIEL.ipynb
```

Or in VS Code, select the "DSI" kernel. Run `DFT+NIEL.ipynb` first since `Geant4_NIEL.ipynb` reads its analytical Coulomb output for the combined NIEL.

## Troubleshooting

### libopenblas.so.0 not found
```bash
export LD_LIBRARY_PATH=$HOME/miniconda3/envs/DSI/lib:$LD_LIBRARY_PATH
```

### MPI "not enough slots" error
Reduce `QE_NPROCS` in the notebook config to match your CPU count:
```bash
nproc  # check available cores
```

### Missing pseudopotential for element X
The JTH PAW v2.0 library covers 86 elements (H-Rn). If you need an element not included, download from:
- https://www.abinit.org/pseudopotential.html (PAW datasets - recommended for consistency)
- https://www.quantum-espresso.org/pseudopotentials/ (PSlibrary)

Place downloaded files in `/usr/share/espresso/pseudo/`

### "S matrix not positive definite" error
This usually means you're mixing PAW and ultrasoft pseudopotentials. Ensure all pseudopotentials are from the same library (JTH PAW). Re-run the installation step 4 if needed.

### Geant4 dataset prompts on import
If `import geant4_pybind` hangs or prompts to download datasets, set the data directory:
```bash
export GEANT4_DATA_DIR=$HOME/geant4-build/build/data
```

### Geant4 "G4RunManager constructed twice" error
The G4RunManager is a singleton. If a notebook cell creates a RunManager, you must restart the kernel before re-running that cell. The Geant4_NIEL notebook is structured to avoid this by creating one RunManager and reusing it across energy points.

### geant4-pybind build fails (no Geant4 found)
Ensure the cmake prefix path is set before pip install:
```bash
export CMAKE_PREFIX_PATH=$HOME/geant4-install:$CMAKE_PREFIX_PATH
export Geant4_DIR=$HOME/geant4-install/lib/cmake/Geant4
pip install geant4-pybind
```
