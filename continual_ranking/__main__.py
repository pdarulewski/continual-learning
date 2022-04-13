import hydra
from pytorch_lightning import seed_everything

from continual_ranking.config.configs import BaseConfig
from continual_ranking.config.paths import CONFIG_DIR
from continual_ranking.experiments.avalanche_baseline import AvalancheBaseline
from continual_ranking.experiments.experiment_runner import ExperimentRunner


@hydra.main(config_path=CONFIG_DIR, config_name='config')
def main(cfg: BaseConfig):
    seed_everything(42)

    if cfg.baseline:
        experiment = AvalancheBaseline(
            model=cfg.model,
            datamodule=cfg.datamodule,
            strategies=cfg.strategies,
            project_name=cfg.project_name,
            max_epochs=cfg.max_epochs,
            cfg=cfg
        )

        experiment.execute()

    else:
        experiment = ExperimentRunner(
            model=cfg.model,
            datamodule=cfg.datamodule,
            strategies=cfg.strategies,
            project_name=cfg.project_name,
            max_epochs=cfg.max_epochs,
            cfg=cfg
        )
        experiment.execute()


if __name__ == '__main__':
    main()