# Copyright The PyTorch Lightning team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import pytest
from torch import optim

import tests.base.develop_utils as tutils
from pytorch_lightning import Trainer
from pytorch_lightning.callbacks import LearningRateMonitor
from pytorch_lightning.utilities.exceptions import MisconfigurationException
from tests.base import BoringModel


def test_lr_monitor_single_lr(tmpdir):
    """ Test that learning rates are extracted and logged for single lr scheduler. """
    tutils.reset_seed()

    # BoringModel already includes single lr scheduler in configure_optimizers method
    model = BoringModel()

    lr_monitor = LearningRateMonitor()
    trainer = Trainer(
        default_root_dir=tmpdir,
        max_epochs=2,
        limit_val_batches=0.1,
        limit_train_batches=0.5,
        callbacks=[lr_monitor],
    )
    result = trainer.fit(model)
    assert result

    assert lr_monitor.lrs, 'No learning rates logged'
    assert all(v is None for v in lr_monitor.last_momentum_values.values()), \
        'Momentum should not be logged by default'
    assert len(lr_monitor.lrs) == len(trainer.lr_schedulers), \
        'Number of learning rates logged does not match number of lr schedulers'
    assert all([k in ['lr-SGD'] for k in lr_monitor.lrs.keys()]), \
        'Names of learning rates not set correctly'


def test_lr_monitor_single_lr_with_momentum(tmpdir):
    """ Test that learning rates and momentum are extracted and logged for single lr scheduler. """
    tutils.reset_seed()

    class SingleLRSchedulerModel(BoringModel):
        def __init__(self):
            super().__init__()
            self.learning_rate = 0.01

        def configure_optimizers(self):
            optimizer = optim.SGD(self.parameters(), lr=self.learning_rate, momentum=0.9)
            lr_scheduler = optim.lr_scheduler.OneCycleLR(optimizer,
                                                         max_lr=self.learning_rate,
                                                         total_steps=10_000)
            return [optimizer], [lr_scheduler]

    model = SingleLRSchedulerModel()

    lr_monitor = LearningRateMonitor(log_momentum=True)
    trainer = Trainer(
        default_root_dir=tmpdir,
        max_epochs=2,
        limit_val_batches=0.1,
        limit_train_batches=0.5,
        callbacks=[lr_monitor],
    )
    result = trainer.fit(model)
    assert result

    assert all(v is not None for v in lr_monitor.last_momentum_values.values()), \
        'Expected momentum to be logged'
    assert len(lr_monitor.last_momentum_values) == len(trainer.lr_schedulers), \
        'Number of momentum values logged does not match number of lr schedulers'
    assert all([k in ['lr-SGD-momentum'] for k in lr_monitor.last_momentum_values.keys()]), \
        'Names of momentum values not set correctly'


def test_lr_monitor_no_lr_scheduler(tmpdir):
    tutils.reset_seed()

    class NoLRSchedulerModel(BoringModel):
        def configure_optimizers(self):
            return optim.SGD(self.parameters(), lr=0.01)

    model = NoLRSchedulerModel()

    lr_monitor = LearningRateMonitor()
    trainer = Trainer(
        default_root_dir=tmpdir,
        max_epochs=2,
        limit_val_batches=0.1,
        limit_train_batches=0.5,
        callbacks=[lr_monitor],
    )

    with pytest.warns(RuntimeWarning, match='have no learning rate schedulers'):
        result = trainer.fit(model)
        assert result


def test_lr_monitor_no_logger(tmpdir):
    tutils.reset_seed()

    model = BoringModel()

    lr_monitor = LearningRateMonitor()
    trainer = Trainer(
        default_root_dir=tmpdir,
        max_epochs=1,
        callbacks=[lr_monitor],
        logger=False
    )

    with pytest.raises(MisconfigurationException, match='Trainer that has no logger'):
        trainer.fit(model)


@pytest.mark.parametrize("logging_interval", ['step', 'epoch'])
def test_lr_monitor_multi_lrs(tmpdir, logging_interval):
    """ Test that learning rates are extracted and logged for multi lr schedulers. """
    tutils.reset_seed()

    class MultiLRSchedulerModel(BoringModel):
        def __init__(self):
            super().__init__()
            self.learning_rate = 0.01

        def training_step(self, batch, batch_idx, optimizer_idx=None):
            return super().training_step(batch, batch_idx)

        def configure_optimizers(self):
            optimizer1 = optim.Adam(self.parameters(), lr=self.learning_rate)
            optimizer2 = optim.Adam(self.parameters(), lr=self.learning_rate)
            lr_scheduler1 = optim.lr_scheduler.StepLR(optimizer1, 1, gamma=0.1)
            lr_scheduler2 = optim.lr_scheduler.StepLR(optimizer2, 1, gamma=0.1)

            return [optimizer1, optimizer2], [lr_scheduler1, lr_scheduler2]

    model = MultiLRSchedulerModel()
    model.training_epoch_end = None

    lr_monitor = LearningRateMonitor(logging_interval=logging_interval)
    log_every_n_steps = 2

    trainer = Trainer(
        default_root_dir=tmpdir,
        max_epochs=2,
        log_every_n_steps=log_every_n_steps,
        limit_train_batches=7,
        limit_val_batches=0.1,
        callbacks=[lr_monitor],
    )
    result = trainer.fit(model)
    assert result

    assert lr_monitor.lrs, 'No learning rates logged'
    assert len(lr_monitor.lrs) == len(trainer.lr_schedulers), \
        'Number of learning rates logged does not match number of lr schedulers'
    assert all([k in ['lr-Adam', 'lr-Adam-1'] for k in lr_monitor.lrs.keys()]), \
        'Names of learning rates not set correctly'

    if logging_interval == 'step':
        expected_number_logged = trainer.global_step // log_every_n_steps
    if logging_interval == 'epoch':
        expected_number_logged = trainer.max_epochs

    assert all(len(lr) == expected_number_logged for lr in lr_monitor.lrs.values()), \
        'Length of logged learning rates do not match the expected number'


def test_lr_monitor_param_groups(tmpdir):
    """ Test that learning rates are extracted and logged for single lr scheduler. """
    tutils.reset_seed()

    class SingleLRSchedulerModel(BoringModel):
        def __init__(self):
            super().__init__()
            self.learning_rate = 0.1

        def configure_optimizers(self):
            param_groups = [
                {'params': list(self.parameters())[:2], 'lr': self.learning_rate * 0.1},
                {'params': list(self.parameters())[2:], 'lr': self.learning_rate}
            ]

            optimizer = optim.Adam(param_groups)
            lr_scheduler = optim.lr_scheduler.StepLR(optimizer, 1, gamma=0.1)
            return [optimizer], [lr_scheduler]

    model = SingleLRSchedulerModel()

    lr_monitor = LearningRateMonitor()
    trainer = Trainer(
        default_root_dir=tmpdir,
        max_epochs=2,
        limit_val_batches=0.1,
        limit_train_batches=0.5,
        callbacks=[lr_monitor],
    )
    result = trainer.fit(model)
    assert result

    assert lr_monitor.lrs, 'No learning rates logged'
    assert len(lr_monitor.lrs) == 2 * len(trainer.lr_schedulers), \
        'Number of learning rates logged does not match number of param groups'
    assert all([k in ['lr-Adam/pg1', 'lr-Adam/pg2'] for k in lr_monitor.lrs.keys()]), \
        'Names of learning rates not set correctly'


def test_lr_monitor_invalid_logging_interval():
    with pytest.raises(MisconfigurationException, match=r'logging_interval should be .*'):
        lr_monitor = LearningRateMonitor(logging_interval='test')
