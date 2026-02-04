# DFT & eDMFT Pipeline Installation Guide (Ubuntu ARM64)

Complete installation instructions for running the DFT + Wannier90 + TRIQS CTHYB pipeline on Ubuntu ARM64 (aarch64).

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

## 4. Build Wannier90 from Source

Wannier90 is not available on conda-forge for ARM64, so we build from source.

```bash
conda activate DSI
cd ~

# download and extract
wget https://github.com/wannier-developers/wannier90/archive/refs/tags/v3.1.0.tar.gz
tar -xzf v3.1.0.tar.gz
cd wannier90-3.1.0

# create make.inc
cat > make.inc << 'EOF'
F90 = gfortran
FCOPTS = -O3 -fPIC
LDOPTS = -O3
COMMS = mpi
MPIF90 = mpif90
LIBS = -L${CONDA_PREFIX}/lib -lopenblas -llapack
EOF

# fix openblas symlink if needed
ln -sf ${CONDA_PREFIX}/lib/libopenblasp-r*.so ${CONDA_PREFIX}/lib/libopenblas_.so 2>/dev/null || true

# build
make -j$(nproc)

# install to conda prefix
cp wannier90.x postw90.x w90chk2chk.x ${CONDA_PREFIX}/bin/
cd ~
rm -rf wannier90-3.1.0 v3.1.0.tar.gz
```

Verify:
```bash
which wannier90.x
wannier90.x --version
```

## 5. Build TRIQS from Source

TRIQS is not available on conda-forge for ARM64.

```bash
conda activate DSI
cd ~

# clone triqs
git clone https://github.com/TRIQS/triqs.git --branch 3.3.x
cd triqs
mkdir build && cd build

# configure
cmake .. \
    -DCMAKE_INSTALL_PREFIX=${CONDA_PREFIX} \
    -DCMAKE_BUILD_TYPE=Release \
    -DPython_EXECUTABLE=$(which python) \
    -DBUILD_SHARED_LIBS=ON

# build and install
make -j$(nproc)
make install

cd ~
rm -rf triqs
```

Verify:
```bash
python -c "import triqs; print(triqs.__version__)"
```

## 6. Build TRIQS CTHYB from Source

```bash
conda activate DSI
cd ~

# clone cthyb
git clone https://github.com/TRIQS/cthyb.git --branch 3.3.x
cd cthyb
mkdir build && cd build

# configure
cmake .. \
    -DCMAKE_INSTALL_PREFIX=${CONDA_PREFIX} \
    -DCMAKE_BUILD_TYPE=Release \
    -DPython_EXECUTABLE=$(which python)

# build and install
make -j$(nproc)
make install

cd ~
rm -rf cthyb
```

Verify:
```bash
python -c "from triqs_cthyb import Solver; print('CTHYB OK')"
```

## 7. Install pw2wannier90

This should come with Quantum ESPRESSO. Verify:
```bash
which pw2wannier90.x
```

If missing, it needs to be built with QE (the conda package should include it).

## 8. Install Pseudopotentials

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

This library is well-tested and suitable for high-throughput calculations with any JARVIS material.

## 9. Register Jupyter Kernel

```bash
conda activate DSI
python -m ipykernel install --user --name DSI --display-name "DSI (TRIQS)"
```

## 10. Environment Variables

Add to `~/.bashrc`:
```bash
echo 'export LD_LIBRARY_PATH=$HOME/miniconda3/envs/DSI/lib:$LD_LIBRARY_PATH' >> ~/.bashrc
source ~/.bashrc
```

## Verification

Run this script to verify all components:

```bash
conda activate DSI

echo "=== Checking executables ==="
for exe in pw.x wannier90.x pw2wannier90.x mpirun; do
    if which $exe > /dev/null 2>&1; then
        echo "OK: $exe -> $(which $exe)"
    else
        echo "MISSING: $exe"
    fi
done

echo ""
echo "=== Checking Python packages ==="
python << 'EOF'
import sys
for pkg in ['numpy', 'ase', 'jarvis', 'triqs', 'nglview', 'pandas']:
    try:
        mod = __import__(pkg)
        ver = getattr(mod, '__version__', 'OK')
        print(f"OK: {pkg} {ver}")
    except ImportError:
        print(f"MISSING: {pkg}")

try:
    from triqs_cthyb import Solver
    print("OK: triqs_cthyb")
except ImportError as e:
    print(f"MISSING: triqs_cthyb ({e})")
EOF

echo ""
echo "=== Checking pseudopotentials ==="
count=$(ls /usr/share/espresso/pseudo/*.UPF /usr/share/espresso/pseudo/*.upf 2>/dev/null | wc -l)
echo "Pseudopotential files: $count"
```

## Running the Notebook

```bash
conda activate DSI
cd /path/to/LUMENS-PV/DFT_eDMFT
jupyter notebook run_pipeline_notebook.ipynb
```

Or in VS Code, select the "DSI (TRIQS)" kernel.

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
This usually means you're mixing PAW and ultrasoft pseudopotentials. Ensure all pseudopotentials are from the same library (JTH PAW). Re-run the installation step 8 if needed.

### TRIQS import errors
Ensure `LD_LIBRARY_PATH` includes the conda lib directory and restart the kernel.
