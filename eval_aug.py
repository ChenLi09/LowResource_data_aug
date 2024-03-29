#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@File    :   eval_aug.py
@Time    :   2020/7/15
@Software:   PyCharm
@Author  :   Li Chen
@Desc    :   
"""

import argparse
import os
import sys
import torch
import torch.nn.functional as F
from torchtext import data
from torchtext.vocab import Vectors
from classifiers.textCNN import TextCNN
import dataset
from mixup import text_mixup as tm


def train(train_iter, val_iter, model, args):
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    steps = 0
    best_acc = 0
    model.train()
    for epoch in range(1, args.epochs+1):
        for batch in train_iter:
            feature, target = batch.text, batch.label
            feature.t_()
            target.data.sub_(1)
            optimizer.zero_grad()

            if args.mixup:
                batch_mix_index = int(target.size()[0] * args.rate_mixup)
                logits, lam = model(feature, is_training=True)
                loss = tm.loss_mixup(logits, target, batch_mix_index, lam)
                logits = logits[:-batch_mix_index]
            else:
                logits, _ = model(feature)
                loss = F.cross_entropy(logits, target)

            loss.backward()
            optimizer.step()
            steps += 1
            if steps % args.log_interval == 0:
                corrects = (torch.max(logits, 1)[1].view(target.size()).data == target.data).sum()
                train_acc = 1.0 * corrects / batch.batch_size
                sys.stdout.write(
                    'Batch[{}] - loss: {:.6f}  acc: {:.4f} ({}/{})'.format(steps,
                                                                             loss.item(),
                                                                             train_acc,
                                                                             corrects,
                                                                             batch.batch_size))
            if steps % args.eval_interval == 0:
                val_acc = eval(val_iter, model, args)
                if val_acc > best_acc:
                    best_acc = val_acc
                    if args.save_checkpoint:
                        print('Saving best model, acc: {:.4f}\n'.format(best_acc))
                        save(model, args.save_dir, 'best', steps)
    print(best_acc.item())


def eval(data_iter, model, args):
    model.eval()
    corrects, avg_loss = 0, 0
    for batch in data_iter:
        feature, target = batch.text, batch.label
        feature.t_()
        target.data.sub_(1)
        logits, _ = model(feature)
        loss = F.cross_entropy(logits, target)
        avg_loss += loss.item()
        corrects += (torch.max(logits, 1)
                     [1].view(target.size()).data == target.data).sum()
    size = len(data_iter.dataset)
    avg_loss /= size
    accuracy = 1.0 * corrects / size
    print('\nEvaluation - loss: {:.6f}  acc: {:.4f} ({}/{}) \n'.format(avg_loss,
                                                                       accuracy,
                                                                       corrects,
                                                                       size))
    return accuracy


def save(model, save_dir, prefix, steps):
    if not os.path.isdir(save_dir):
        os.makedirs(save_dir)
    save_prefix = os.path.join(save_dir, prefix)
    save_path = '{}_steps_{}.pt'.format(save_prefix, steps)
    torch.save(model.state_dict(), save_path)


def load_word_vectors(w2v_name, w2v_path):
    vectors = Vectors(name=w2v_name, cache=w2v_path)
    return vectors


def load_dataset(text_field, label_field, args, **kwargs):
    train_dataset, val_dataset = dataset.make_dataset(args.train_file, args.test_file, text_field, label_field)
    vectors = load_word_vectors(args.w2v_name, args.w2v_path)
    text_field.build_vocab(train_dataset, val_dataset, vectors=vectors)
    label_field.build_vocab(train_dataset, val_dataset)
    train_iter, val_iter = data.Iterator.splits(
        (train_dataset, val_dataset),
        batch_sizes=(args.batch_size, len(val_dataset)),
        sort_key=lambda x: len(x.text),
        **kwargs)
    return train_iter, val_iter


def main():
    parser = argparse.ArgumentParser(description='text classifier')
    # learning
    parser.add_argument('--lr', type=float, default=0.001, help='initial learning rate [default: 0.001]')
    parser.add_argument('--epochs', type=int, default=5, help='number of epochs for train [default: 256]')
    parser.add_argument('--batch_size', type=int, default=20, help='batch size for training [default: 128]')
    parser.add_argument('--log_interval', type=int, default=5,
                        help='how many steps to wait before logging training status [default: 1]')
    parser.add_argument('--eval_interval', type=int, default=5,
                        help='how many steps to wait before testing [default: 100]')
    parser.add_argument('--save_dir', type=str, default='ckp/', help='where to save the snapshot')
    parser.add_argument('--save_checkpoint', type=bool, default=False, help='whether to save when get best performance')
    # model
    parser.add_argument('--dropout', type=float, default=0.5, help='the probability for dropout [default: 0.5]')
    parser.add_argument('--max_norm', type=float, default=3.0, help='l2 constraint of parameters [default: 3.0]')
    parser.add_argument('--embedding_dim', type=int, default=300, help='number of embedding dimension [default: 128]')
    parser.add_argument('--filter_num', type=int, default=100, help='number of each size of filter')
    parser.add_argument('--filter_sizes', type=str, default='3,4,5',
                        help='comma-separated filter sizes to use for convolution')
    # load file
    parser.add_argument('--w2v_name', type=str, default='sgns.wiki.word',
                        help='filename of pre-trained word vectors')
    parser.add_argument('--w2v_path', type=str, default='data/', help='path of pre-trained word vectors')
    parser.add_argument('--train_file', type=str, required=True, help='path of train set')
    parser.add_argument('--test_file', type=str, required=True, help='path of test set')
    # device
    parser.add_argument('--device', type=int, default=-1,
                     help='device to use for iterate data, -1 mean cpu [default: -1]')
    # option
    parser.add_argument('--snapshot', type=str, default=None, help='filename of model snapshot [default: None]')
    # isMixup
    parser.add_argument('--mixup', type=str, default=None, help='the method of textMixup [default: None]')
    parser.add_argument('--rate_mixup', type=float, default=0.5, help='the rate of mixup data [default: 0.5]')
    parser.add_argument('--alpha', type=float, default=1.0, help='hyper-parameter [default: 1.0]')

    args = parser.parse_args()
    print('Loading data...')
    text_field = data.Field(lower=True)
    label_field = data.Field(sequential=False)
    train_iter, val_iter = load_dataset(text_field, label_field, args, repeat=False, shuffle=True)

    args.vocabulary_size = len(text_field.vocab)
    args.embedding_dim = text_field.vocab.vectors.size()[-1]
    args.vectors = text_field.vocab.vectors
    args.class_num = len(label_field.vocab)
    args.filter_sizes = [int(size) for size in args.filter_sizes.split(',')]

    classifier = TextCNN(args)
    if args.snapshot:
        print('\nLoading model from {}...\n'.format(args.snapshot))
        classifier.load_state_dict(torch.load(args.snapshot))

    try:
        train(train_iter, val_iter, classifier, args)
    except KeyboardInterrupt:
        print('Exit from training early')


if __name__ == '__main__':
    main()
