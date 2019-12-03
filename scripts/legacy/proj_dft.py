import numpy as np
from pyscf import gto
import os
import sys
import argparse
import mendeleev

aa = 2.0**np.arange(6,-3,-1)
bb = np.diag(np.ones(aa.size)) - np.diag(np.ones(aa.size-1), k=1)
coef = np.concatenate([aa.reshape(-1,1), bb], axis=1)
BASIS = [[0, *coef.tolist()], [1, *coef.tolist()], [2, *coef.tolist()]]

def parse_xyz(filename, basis='ccpvtz', verbose=False):
    with open(filename) as fp:
        natoms = int(fp.readline())
        comments = fp.readline()
        xyz_str = "".join(fp.readlines())
    mol = gto.Mole()
    mol.verbose = 4 if verbose else 0
    mol.atom = xyz_str
    mol.basis  = basis
    try:
        mol.build(0,0,unit="Ang")
    except RuntimeError as e:
        mol.spin = 1
        mol.build(0,0,unit="Ang")
    return mol  


def gen_proj(mol, 
             test_name, 
             test_basis, 
             intor = 'ovlp',
             verbose = False) :

    natm = mol.natm
    mole_coords = mol.atom_coords(unit="Ang")
    test_mol = gto.Mole()
    if verbose :
        test_mol.verbose = 4
    else :
        test_mol.verbose = 0
    test_mol.atom = [[test_name, coord] for coord in mole_coords]
    test_mol.basis = BASIS
    test_mol.spin = mendeleev.element(test_name).atomic_number * natm % 2
    test_mol.build(0,0,unit="Ang")
    proj = gto.intor_cross(f'int1e_{intor}_sph', mol, test_mol) 
    
    def proj_func(mo):
        proj_coeff = np.matmul(mo, proj).reshape(*mo.shape[:2], natm, -1)
        if verbose:
            print('shape of coeff data          ', proj_coeff.shape)
        # res : nframe x nocc/nvir x natm x nproj
        return proj_coeff, proj_coeff.shape[-1]
    
    return proj_func


def load_data(dir_name):
    meta = np.loadtxt(os.path.join(dir_name, 'system.raw'), dtype=int).reshape(-1)
    natm = meta[0]
    nao = meta[1]
    nocc = meta[2]
    nvir = meta[3]
    e_dft = np.loadtxt(os.path.join(dir_name, 'e_dft.raw')).reshape(-1, 1)
    e_data = [np.loadtxt(os.path.join(dir_name, 'ener_occ.raw')).reshape(-1, nocc),
              np.loadtxt(os.path.join(dir_name, 'ener_vir.raw')).reshape(-1, nvir)]
    c_data = [np.loadtxt(os.path.join(dir_name, 'coeff_occ.raw')).reshape([-1, nocc, nao]),
              np.loadtxt(os.path.join(dir_name, 'coeff_vir.raw')).reshape([-1, nvir, nao])]
    return meta, e_dft, e_data, c_data


def dump_data(dir_name, meta, e_dft, e_data, c_data) :
    os.makedirs(dir_name, exist_ok = True)
    np.savetxt(os.path.join(dir_name, 'system.raw'), 
               meta.reshape(1,-1), 
               fmt = '%d',
               header = 'natm nao nocc nvir nproj')
    nframe = e_data[0].shape[0]
    natm = meta[0]
    nao = meta[1]
    nocc = meta[2]
    nvir = meta[3]
    nproj = meta[4]
    # ntest == natm
    assert(all(c_data[0].shape == np.array([nframe, nocc, natm, nproj], dtype = int)))
    assert(all(c_data[1].shape == np.array([nframe, nvir, natm, nproj], dtype = int)))
    assert(all(e_data[0].shape == np.array([nframe, nocc], dtype = int)))
    assert(all(e_data[1].shape == np.array([nframe, nvir], dtype = int)))
    np.save(os.path.join(dir_name, 'e_dft.npy'), e_dft) 
    np.save(os.path.join(dir_name, 'ener_occ.npy'), e_data[0])
    np.save(os.path.join(dir_name, 'ener_vir.npy'), e_data[1])
    np.save(os.path.join(dir_name, 'coeff_occ.npy'), c_data[0])
    np.save(os.path.join(dir_name, 'coeff_vir.npy'), c_data[1])


def proj_frame(xyz_file, mo_dir, dump_dir=None, test_name="Ne", test_basis="ccpvtz", intor='ovlp', verbose=False):
    mol = parse_xyz(xyz_file)
    meta, e_dft, e_data, c_data = load_data(mo_dir)
    
    proj_func = gen_proj(mol, test_name, test_basis, intor, verbose)
    c_proj_occ,nproj = proj_func(c_data[0])
    c_proj_vir,nproj = proj_func(c_data[1])

    c_data = (c_proj_occ, c_proj_vir)
    meta = np.append(meta, nproj)
    # print(meta, c_proj_occ.shape)

    if dump_dir is not None:
        dump_data(dump_dir, meta, e_dft, e_data, c_data)
    return meta, e_dft, e_data, c_data


def main():
    parser = argparse.ArgumentParser(description="Calculate and save mp2 energy and mo_coeffs for given xyz files.")
    parser.add_argument("-x", "--xyz-file", nargs="+", help="input xyz file(s), if more than one, concat them")
    parser.add_argument("-f", "--mo-dir", nargs="+", help="input mo folder(s), must of same number with xyz files")
    parser.add_argument("-d", "--dump-dir", default=".", help="dir of dumped files, if not specified, use current folder")
    parser.add_argument("-v", "--verbose", action='store_true', help="output calculation information")
    parser.add_argument("-E", "--element", default="Ne", help="element symbol to use as test orbitals")
    parser.add_argument("-B", "--basis", default="ccpvtz", help="atom basis to use as test orbitals, could be a string or a file path")
    parser.add_argument("-I", "--intor", default="ovlp", help="intor string used to calculate int1e")
    args = parser.parse_args()

    assert len(args.xyz_file) == len(args.mo_dir)
    oldmeta = None
    all_e_dft = []
    all_e_occ = []
    all_e_vir = []
    all_c_occ = []
    all_c_vir = []
    for xf, md in zip(args.xyz_file, args.mo_dir):
        meta, e_dft, e_data, c_data = proj_frame(xf, md, 
                                                        test_name=args.element, 
                                                        test_basis=args.basis, 
                                                        intor=args.intor,
                                                        verbose=args.verbose)
        if oldmeta is not None:
            assert all(oldmeta == meta), "all frames has to be in the same system thus meta has to be equal!"
        oldmeta = meta
        all_e_dft.append(e_dft)
        all_e_occ.append(e_data[0])
        all_e_vir.append(e_data[1])
        all_c_occ.append(c_data[0])
        all_c_vir.append(c_data[1])
        print(f"{xf} && {md} finished")
    all_e_dft = np.concatenate(all_e_dft)
    all_e_occ = np.concatenate(all_e_occ)
    all_e_vir = np.concatenate(all_e_vir)
    all_c_occ = np.concatenate(all_c_occ)
    all_c_vir = np.concatenate(all_c_vir)

    dump_data(args.dump_dir, meta, all_e_dft, (all_e_occ, all_e_vir), (all_c_occ, all_c_vir))
    print("done")

if __name__ == "__main__":
    main()