import argparse, os
import numpy as np
import torch
if __name__ == "__main__":
    import sys
    sys.path.append(os.path.dirname(os.path.realpath(__file__)) + "/../../")
from deepqc.train.model import QCNet
from deepqc.train.reader import GroupReader
from deepqc.train.train import DEVICE, train, preprocess
from deepqc.utils import load_yaml, load_sys_dirs


def main(restart=None, **argdict):
   
    seed = argdict.get('seed', np.random.randint(0, 2**32))
    print(f'# using seed: {seed}')
    np.random.seed(seed)
    torch.manual_seed(seed)

    train_paths = load_sys_dirs(argdict['train_paths'])
    print(f'# training with {len(train_paths)} system(s)')
    g_reader = GroupReader(train_paths, **argdict['data_args'])
    if 'test_paths' in argdict:
        test_paths = load_sys_dirs(argdict['test_paths'])
        print(f'# testing with {len(test_paths)} system(s)')
        test_reader = GroupReader(test_paths, **argdict['data_args'])
    else:
        print('# testing with training set')
        test_reader = None

    if restart is not None:
        model = QCNet.load(restart)
    else:
        model = QCNet(**argdict['model_args'])
    preprocess(model, g_reader, **argdict['preprocess_args'])
    model = model.double().to(DEVICE)

    train(model, g_reader, test_reader=test_reader, **argdict['train_args'])


def cli():
    parser = argparse.ArgumentParser(
        description="Train a model according to given input.")
    parser.add_argument('input', type=str, 
                        help='the input yaml file for args')
    parser.add_argument('--restart', default=None,
                        help='the restart file to load model from, would ignore model_args if given')
    args = parser.parse_args()
    argdict = load_yaml(args.input)

    main(restart=args.restart, **argdict)


if __name__ == "__main__":
    cli()