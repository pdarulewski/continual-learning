import gc
import linecache
import logging
import time
import tracemalloc

import torch
import wandb
from omegaconf import DictConfig
from omegaconf import OmegaConf

from continual_ranking.dpr.data.file_handler import pickle_dump
from continual_ranking.dpr.evaluator import Evaluator
from continual_ranking.experiment.base import Base

logger = logging.getLogger(__name__)


def display_top(snapshot, key_type='lineno', limit=20):
    snapshot = snapshot.filter_traces((
        tracemalloc.Filter(False, "<frozen importlib._bootstrap>"),
    ))
    top_stats = snapshot.statistics(key_type)

    logger.info("Top %s lines" % limit)
    for index, stat in enumerate(top_stats[:limit], 1):
        frame = stat.traceback[0]
        logger.info("#%s: %s:%s: %.1f KiB"
                    % (index, frame.filename, frame.lineno, stat.size / 1024))
        line = linecache.getline(frame.filename, frame.lineno).strip()
        if line:
            logger.info('    %s' % line)

    other = top_stats[limit:]
    if other:
        size = sum(stat.size for stat in other)
        logger.info("%s other: %.1f KiB" % (len(other), size / 1024))
    total = sum(stat.size for stat in top_stats)
    logger.info("Total allocated size: %.1f KiB" % (total / 1024))


class Experiment(Base):

    def __init__(self, cfg: DictConfig):
        super().__init__(cfg)

        self.experiment_id: int = 0
        self.training_time: float = 0

        self.index_path: str = ''
        self.test_path: str = ''

    def wandb_log(self, metrics: dict):
        if self.logging_on:
            wandb.log(metrics)

    def run_training(self) -> None:
        self.alert(
            title=f'Training for {self.experiment_name} started!',
            text=f'```\n{OmegaConf.to_yaml(self.cfg)}```'
        )

        id_ = self.cfg.experiment.get('id')

        tracemalloc.start()
        for i, (train_dataloader, val_dataloader) in enumerate(zip(self.train_dataloader, self.val_dataloader)):
            if i == 0:
                snapshot_1 = tracemalloc.take_snapshot()
                display_top(snapshot_1)

            self.model.train_length = len(train_dataloader.dataset)
            self.model.val_length = len(val_dataloader.dataset)

            self.alert(
                title=f'Experiment #{i} for {self.experiment_name} started!',
                text=f'Training dataloader size: {len(train_dataloader.dataset)}\n'
                     f'Validation dataloader size: {len(val_dataloader.dataset)}'
            )

            self.experiment_id = i if not id_ else id_
            self.model.experiment_id = self.experiment_id
            self.trainer.task_id = self.experiment_id

            start = time.time()
            self.trainer.fit(self.model, train_dataloader, val_dataloader)
            experiment_time = time.time() - start

            self.training_time += experiment_time
            self.wandb_log({'experiment_time': experiment_time, 'experiment_id': self.experiment_id})

            torch.cuda.empty_cache()
            self._evaluate()
            torch.cuda.empty_cache()

            gc.collect()

            snapshot_2 = tracemalloc.take_snapshot()
            top_stats = snapshot_2.compare_to(snapshot_1, 'lineno')
            for stat in top_stats[:20]:
                logger.info(stat)
            display_top(snapshot_2)

        self.wandb_log({'training_time': self.training_time})

    def _index(self, index_dataloader) -> None:
        self.alert(
            title=f'Indexing for {self.experiment_name} started!',
            text=f'Index dataloader size: {len(index_dataloader.dataset)}'
        )

        self.model.index_mode = True
        self.trainer.test(self.model, index_dataloader)
        self.model.index_mode = False

        self.index_path = f'index_{self.experiment_name}_{self.experiment_id}'

        self.alert(
            title=f'Indexing finished!',
            text=f'Indexed {len(self.model.index)} samples, index shape: {self.model.index.shape}'
        )

        pickle_dump(self.model.index, self.index_path)
        self.model.index = []

    def _test(self, test_dataloader) -> None:
        self.alert(
            title=f'Testing for {self.experiment_name} #{self.experiment_id} started!',
            text=f'Test dataloader size: {len(test_dataloader.dataset)}'
        )

        self.model.test_length = len(test_dataloader.dataset)

        self.trainer.test(self.model, test_dataloader)

        self.alert(
            title=f'Testing finished!',
            text=f'Tested {self.model.test_length} samples, test shape: {self.model.test.shape}'
        )

        self.test_path = f'test_{self.experiment_name}_{self.experiment_id}'
        pickle_dump(self.model.test, self.test_path)
        self.model.test = []

    def _evaluate(self) -> None:
        index_dataloader = self.datamodule.index_dataloader()
        test_dataloader = self.datamodule.test_dataloader()

        self._index(index_dataloader)
        self._test(test_dataloader)

        self.alert(title=f'Evaluation for {self.experiment_name} #{self.experiment_id} started!')

        evaluator = Evaluator(
            self.cfg.biencoder.sequence_length,
            index_dataloader.dataset, self.index_path,
            test_dataloader.dataset, self.test_path,
            'cuda:0' if self.cfg.device == 'gpu' else 'cpu',
            self.experiment_id
        )

        scores = evaluator.evaluate()

        self.wandb_log(scores)

        self.alert(
            title=f'Evaluation finished!',
            text=f'```{scores}```'
        )
