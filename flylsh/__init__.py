import numpy as np
import scipy.sparse

def mean_shift_nonzero_sparse(data):
    # probably inplace
    assert scipy.sparse.isspmatrix_csr(data), 'must use csr format'
    # adjust zero elements only ... kind of strange
    m = np.array(data.sum(axis=1)).squeeze()
    # nonzero_per_row = np.diff(data.indptr) # https://stackoverflow.com/questions/3797158/counting-non-zero-elements-within-each-row-and-within-each-column-of-a-2d-numpy
    nonzero_per_row = data.getnnz(axis=1)
    data_mean = m / np.maximum(0, nonzero_per_row)
    data.data -= data_mean[data.indices]
    return data

class flylsh(object):
    def __init__(self, data, hash_length, sampling_ratio, embedding_size):
        """
        data: Nxd matrix
        hash_length: scalar
        sampling_ratio: fraction of input dims to sample from when producing a hash
        embedding_size: dimensionality of projection space, m
        Note that in Flylsh, the hash length and embedding_size are NOT the same
        whereas in usual LSH they are
        """
        self.embedding_size = embedding_size
        if scipy.sparse.issparse(data): # sparse random projections might not make sense for sparse inputs, just messing around
            self.data = data
            mean_shift_nonzero_sparse(self.data)
        else:
            self.data = (data - np.mean(data, axis=1)[:, None])
        weights = np.random.random((data.shape[1], embedding_size)) # TODO think about sparse inputs here
        self.weights = (weights > 1 - sampling_ratio)  # sparse projection vectors
        all_activations = (self.data @ self.weights) # @ is np.matmul
        # nth largest for each row, see np or bottleneck partition as well
        threshold = np.sort(all_activations, axis=1)[:, -hash_length][:, None]
        self.hashes = (all_activations >= threshold)  # choose topk activations, set rest to zero

    def query(self, qidx, nnn):
        """ get nearest neighbours """
        L1_distances = np.sum(np.abs(np.logical_xor(self.hashes[qidx, :], self.hashes).astype(int)), axis=1)
        # _L1_distances = np.sum(np.abs(self.hashes[qidx, :].astype(int) - self.hashes.astype(int)), axis=1) # '-' boolean is deprecated
        # check = L1_distances.astype(int) - _L1_distances
        # assert np.max(np.abs(check)) == 0, 'not ok'
        # print('yep ok')
        NNs = L1_distances.argsort()[1:nnn + 1]
        # print(L1_distances[NNs]) #an interesting property of this hash is that the L1 distances are always even
        return NNs

    def true_nns(self, qidx, nnn):
        sample = self.data[qidx, :]
        return np.sum((self.data - sample)**2, axis=1).argsort()[1:nnn + 1]

    def construct_true_nns(self, indices, nnn):
        all_NNs = np.zeros((len(indices), nnn))
        for idx1, idx2 in enumerate(indices):
            all_NNs[idx1, :] = self.true_nns(idx2, nnn)
        return all_NNs

    def AP(self, predictions, truth):
        assert len(predictions) == len(truth)
        precisions = [len(list(set(predictions[:idx]).intersection(set(truth[:idx])))) / idx for
                      idx in range(1, len(truth) + 1)]
        return np.mean(precisions)

    def findmAP(self, nnn, n_points):
        start = np.random.randint(low=0, high=self.data.shape[0] - n_points)
        sample_indices = np.arange(start, start + n_points)
        all_NNs = self.construct_true_nns(sample_indices, nnn)
        self.allAPs = []
        for eidx, didx in enumerate(sample_indices):
            # eidx: enumeration id, didx: index of sample in self.data
            this_nns = self.query(didx, nnn)
            this_AP = self.AP(list(this_nns), list(all_NNs[eidx, :]))
            # print(this_AP)
            self.allAPs.append(this_AP)

        return np.mean(self.allAPs)
