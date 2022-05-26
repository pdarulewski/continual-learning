import logging
from copy import deepcopy
from typing import Union

import pytorch_lightning as pl
import torch
from torch.utils.data import DataLoader

from continual_ranking.continual_learning.continual_trainer import ContinualTrainer
from continual_ranking.continual_learning.strategy import Strategy
from continual_ranking.dpr.models import BiEncoder

logger = logging.getLogger(__name__)


class EWC(Strategy):
    def __init__(self, ewc_lambda: float):
        super().__init__()
        self.ewc_lambda = ewc_lambda

        self.device = None
        self.params = {}
        self._means = {}
        self.fisher_matrix = {}

        for n, p in deepcopy(self.params).items():
            self._means[n] = p.data

    def _diag_fisher(self, pl_module: Union["pl.LightningModule", BiEncoder], dataloader: DataLoader):
        precision_matrices = {}
        for n, p in deepcopy(self.params).items():
            p.data.zero_()
            precision_matrices[n] = p.data

        pl_module.eval()
        for batch_idx, batch in enumerate(dataloader):
            pl_module.zero_grad()
            batch.to(self.device)
            loss, _, _ = pl_module.shared_step(batch, batch_idx)
            loss.backward()

            for n, p in pl_module.named_parameters():
                precision_matrices[n].data += p.grad.data ** 2 / len(dataloader)

        precision_matrices = {n: p for n, p in precision_matrices.items()}
        return precision_matrices

    def _penalty(self, pl_module: "pl.LightningModule"):
        loss = 0
        for n, p in pl_module.named_parameters():
            _loss = self.fisher_matrix[n] * (p - self._means[n]) ** 2
            loss += _loss.sum()
        return loss

    def on_train_start(self, trainer: ContinualTrainer, pl_module: "pl.LightningModule") -> None:
        self.device = pl_module.device
        if trainer.task_id > 0:
            self.params = {n: p for n, p in pl_module.named_parameters() if p.requires_grad}
            self.fisher_matrix = self._diag_fisher(pl_module, trainer.train_dataloader)

    def on_before_backward(
            self, trainer: ContinualTrainer, pl_module: "pl.LightningModule", loss: torch.Tensor
    ) -> torch.Tensor:
        loss += self.ewc_lambda * self._penalty(pl_module)
        return loss
