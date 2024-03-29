import tensorflow as tf
import cvae.utils as utils
import numpy as np
import os
import random


class Tokenizer:
    def __init__(self, word_level=False):
        self.word_level = word_level

    def tokenize(self, utter):
        if self.word_level:
            return utter.split()
        else:
            return list(''.join(utter.split()))


def _safe_token2id(vocab, unk_id, token):
    if token in vocab:
        return vocab[token]
    else:
        return unk_id


def _safe_list2ids(vocab, unk_id, tokens):
    return [vocab[t] if t in vocab else unk_id for t in tokens]


# ref: https://stackoverflow.com/questions/47939537/how-to-use-dataset-api-to-read-tfrecords-file-of-lists-of-variant-length
# ref: https://blog.csdn.net/qq1483661204/article/details/78932389
def gen_tfrecord(vocab, intent2id, infiles, outfiles, logger, max_len, word_level=False, shuffle=False):
    """
    generate tfrecord files based on the file given by infile.
    Only the index of each word is saved
    :param vocab: dict from word to index
    :param infiles: input file
    :param outfiles: output file
    :param logger: logger to tell the world what happened
    :param word_level: ture to use word level input
    :return:
    Returns nothing, but generate a outfile file for the generated tfrecord
    """
    def _int64_feature(value):
        return tf.train.Feature(int64_list=tf.train.Int64List(value=value))

    tokenizer = Tokenizer(word_level=word_level)
    assert len(infiles) == len(outfiles)

    writers = []
    for outfile in outfiles:
        writers.append(tf.python_io.TFRecordWriter(outfile))

    count = 0
    for index, infile in enumerate(infiles):
        logger.info('handling {}:{}'.format(index, infile))
        with open(infile, 'r', encoding='utf-8') as f:
            inputs = [i.split('\t') for i in f.readlines() if len(i.strip()) != 0]
            inputs = [i for i in inputs if len(i) >= 3]
            if shuffle:
                random.shuffle(inputs)

            for input in inputs:
                utt = tokenizer.tokenize(input[2])
                if len(utt) == 0:
                    continue
                utt = [utils._GO] + utt[:max_len - 2] + [utils._EOS]
                utt = _safe_list2ids(vocab, vocab[utils._UNK], utt)
                intent = _safe_token2id(intent2id, intent2id[utils._UNK], input[1].lower())#intent:16 fixed by 99 当测试集中出现训练集没有的intent

                features = dict()
                features["utter"] = _int64_feature(utt)
                features["len"] = _int64_feature([len(utt)])
                features["intent"] = _int64_feature([intent])
                features["id"] = _int64_feature([count])
                count += 1

                example = tf.train.Example(features=tf.train.Features(feature=features))
                writers[index].write(example.SerializeToString())

    for index, writer in enumerate(writers):
        logger.info('Finished, generated tfrecord_file: {}'.format(outfiles[index]))
        writer.close()


def check_tfrecord(ids2char, ids2intent, file, n):
    record_iter = tf.python_io.tf_record_iterator(path=file)
    count = 0
    for record in record_iter:
        if count > n:
            break
        example = tf.train.Example()
        example.ParseFromString(record)
        print("utter", [ids2char[i] for i in example.features.feature["utter"].int64_list.value])
        print("len", example.features.feature["len"].int64_list.value)
        print("intent", [ids2intent[i] for i in example.features.feature["intent"].int64_list.value])
        count += 1


