import os
import random
from typing import Optional

import hydra
import pytorch_lightning as pl
from torch.utils.data import DataLoader

from continual_ranking.dpr.data.file_handler import read_json_file
from continual_ranking.dpr.data.index_dataset import IndexDataset
from continual_ranking.dpr.data.training_dataset import TrainingDataset


class DataModule(pl.LightningDataModule):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg

        self.train_set_path = os.path.join(hydra.utils.get_original_cwd(), self.cfg.datasets.train)
        self.eval_set_path = os.path.join(hydra.utils.get_original_cwd(), self.cfg.datasets.val)
        self.index_set_path = os.path.join(hydra.utils.get_original_cwd(), self.cfg.datasets.index)
        self.test_set_path = os.path.join(hydra.utils.get_original_cwd(), self.cfg.datasets.test)

        self.train_sets = None
        self.eval_sets = None
        self.index_set = None
        self.test_sets = None

        self.train_set_length = 0

    def _make_set_splits(self, dataset_path: str, split_size: float = 0):
        data = read_json_file(dataset_path)
        random.shuffle(data)
        chunks = []

        chunk_sizes = self.cfg.run_type.sizes

        if split_size:
            chunk_sizes = [int(size * split_size) for size in chunk_sizes]

        if self.cfg.run_type.baseline:
            chunks = data[:chunk_sizes[-1]]
            chunks = [TrainingDataset(chunks, self.cfg.negatives_amount)]

        else:
            for i in range(len(chunk_sizes) - 1):
                slice_ = data[chunk_sizes[i]: chunk_sizes[i + 1]]
                chunks.append(slice_)
            chunks = [TrainingDataset(chunk, self.cfg.negatives_amount) for chunk in chunks]

        return chunks

    def prepare_data(self) -> None:
        pass

    def setup(self, stage: Optional[str] = None):
        self.train_sets = self._make_set_splits(self.train_set_path)
        self.eval_sets = self._make_set_splits(self.eval_set_path, self.cfg.datasets.split_size)

        if self.cfg.run_type.baseline:
            self.train_set_length = len(self.train_sets)
        else:
            self.train_set_length = sum([len(dataset) for dataset in self.train_sets])

        self.index_set = IndexDataset(read_json_file(self.index_set_path))

    def train_dataloader(self):
        return [
            DataLoader(
                train_set, batch_size=self.cfg.biencoder.batch_size, num_workers=self.cfg.biencoder.num_workers
            ) for train_set in self.train_sets
        ]

    def val_dataloader(self):
        return [
            DataLoader(
                eval_set, batch_size=self.cfg.biencoder.eval_batch_size, num_workers=self.cfg.biencoder.num_workers
            ) for eval_set in self.eval_sets
        ]

    def index_dataloader(self):
        return DataLoader(
            self.index_set, batch_size=self.cfg.biencoder.index_batch_size, num_workers=self.cfg.biencoder.num_workers
        )

    def _test_dataloader(self):
        pass

    def test_dataloader(self):
        pass
