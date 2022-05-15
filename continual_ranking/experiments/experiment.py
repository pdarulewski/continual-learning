from abc import ABC, abstractmethod
from typing import List, Union, Optional, Iterable, Any

import pytorch_lightning as pl
import wandb
from omegaconf import DictConfig
from torch.utils.data import DataLoader

from continual_ranking.continual_learning.continual_trainer import ContinualTrainer


class Experiment(ABC):

    def __init__(self, cfg: DictConfig = None):
        self.model: Optional[pl.LightningModule] = None
        self.datamodule: Optional[pl.LightningDataModule] = None
        self.strategies: Optional[Iterable[pl.Callback]] = None
        self.loggers: list = []

        self.trainer: Optional[Union[ContinualTrainer, Any]] = None

        self.train_dataloader: Union[DataLoader, List[DataLoader]] = []
        self.val_dataloader: Union[DataLoader, List[DataLoader]] = []
        self.index_dataloader: Union[DataLoader, List[DataLoader]] = []
        self.test_dataloader: Union[DataLoader, List[DataLoader]] = []

        self.callbacks: List[pl.Callback] = []

        self.global_step = 0
        self.epochs_completed = 0

        self.cfg = cfg

        self.fast_dev_run = cfg.fast_dev_run
        self.logging_on = cfg.logging_on
        self.experiment_id = 0
        self.index_path = ''
        self.test_path = ''

        self.experiment_name = self.cfg.experiment.name

    def alert(self, title: str, text: str = '', **kwargs):
        if self.logging_on:
            wandb.alert(title=title, text=text, **kwargs)

    @abstractmethod
    def prepare_dataloaders(self) -> None:
        """Prepare and assign the dataloaders"""

    @abstractmethod
    def setup_loggers(self) -> None:
        """Prepare and assign the loggers"""

    @abstractmethod
    def setup_strategies(self) -> None:
        """Prepare and assign the CL strategies, this should be assigned
        to other callbacks"""

    @abstractmethod
    def setup_callbacks(self) -> None:
        """Pass callbacks"""

    @abstractmethod
    def setup_model(self) -> None:
        """Prepare and assign the model"""

    @abstractmethod
    def setup_trainer(self) -> None:
        """Prepare and assign the trainer"""

    def setup(self) -> None:
        self.setup_loggers()
        self.prepare_dataloaders()
        self.setup_model()
        self.setup_strategies()
        self.setup_callbacks()

    @abstractmethod
    def run_training(self):
        """Run training loop"""

    @abstractmethod
    def run_testing(self):
        """Run testing loop"""

    def execute(self):
        try:
            self.setup()
            self.run_training()
            self.run_testing()

        except Exception as e:
            self.alert(
                title='Run has crashed!',
                text=f'Error: {e}',
                level=wandb.AlertLevel.ERROR
            )
            raise
