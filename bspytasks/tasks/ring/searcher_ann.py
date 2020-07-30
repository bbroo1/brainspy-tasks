
import os
import pickle
import numpy as np
import matplotlib.pyplot as plt

from bspyproc.utils.pytorch import TorchUtils
from bspyalgo.utils.io import load_configs
from bspytasks.tasks.ring.classifier import RingClassificationTask as Task
from bspytasks.tasks.ring.data_loader import RingDataLoader

from bspyalgo.utils.io import create_directory, create_directory_timestamp

from bspyalgo.utils.performance import accuracy


class RingSearcher():

    def __init__(self, configs, is_main=True):
        self.configs = configs
        self.is_main = is_main
        self.base_dir = configs['results_base_dir']
        self.task = Task(configs, is_main=False)
        self.data_loader = RingDataLoader(configs)

    def init_dirs(self, gap):
        main_dir = f'searcher_{gap}mV'
        search_stats_dir = 'search_stats'

        if self.is_main:
            base_dir = create_directory_timestamp(self.base_dir, main_dir)
        else:
            base_dir = os.path.join(self.base_dir, main_dir)
            create_directory(base_dir)
        self.search_stats_dir = os.path.join(base_dir, search_stats_dir)
        self.accuracy_plots_dir = os.path.join(base_dir, 'results', 'accuracies')
        create_directory(self.accuracy_plots_dir)
        create_directory(self.search_stats_dir)

        self.task.init_dirs(base_dir, is_main=False)

    def reset(self, output_shape):
        self.task.reset()
        self.performance_per_run = np.zeros(self.configs['runs'])
        self.correlation_per_run = np.zeros(self.configs['runs'])
        self.accuracy_per_run = np.zeros(self.configs['runs'])
        self.val_accuracy_per_run = np.zeros(self.configs['runs'])
        self.outputs_per_run = np.zeros((self.configs['runs'], output_shape))
        self.control_voltages_per_run = np.zeros(self.configs['runs'])
        # self.control_voltages_per_run = np.zeros((self.configs['runs'], self.task.algorithm.processor.control_voltage_no))
        self.seeds_per_run = np.zeros(self.configs['runs'])
        self.best_run = None

    def search_solution(self, gap):
        self.init_dirs(gap)

        self.task.configs['ring_data']['gap'] = gap
        inputs, targets, mask = self.data_loader.get_data(self.configs['algorithm_configs']['processor'], gap=gap)

        self.reset(inputs.shape[0])
        for run in range(self.configs['runs']):
            print(f'########### RUN {run} ################')
            seed = TorchUtils.init_seed(None, deterministic=True)
            results = self.task.run_task(inputs, targets, mask, accuracy_plot_dir=os.path.join(self.accuracy_plots_dir, f'accuracy_plot_{run}.jpg'))
            results['seed'] = seed
            results = self.validate_solution(results, run)
            self.update_search_stats(results, run)
            if self.best_run == None or results['best_performance'] < self.best_run['best_performance']:
                self.update_best_run(results, run)
                self.task.plot_results(results)
        self.close_search(gap)

    def validate_solution(self, results, run):
        inputs, targets, mask = self.data_loader.get_data(self.configs['algorithm_configs']['processor'], gap=self.task.configs['ring_data']['gap'], istest=True)
        with torch.no_grad():
            processor = self.task.algorithm.processor
            processor.eval()
            validation_result = processor(inputs)
            results['test_accuracy'] = accuracy(validation_result[mask].detach().cpu().numpy(),
                                                targets[mask].detach().cpu().numpy(),
                                                plot=os.path.join(self.accuracy_plots_dir, f'test_accuracy{run}.jpg'), node=results['accuracy_node'])
            results['test_inputs'] = inputs
            results['test_targets'] = targets
            results['test_mask'] = mask
            print('Accuracies: ')
            print(f"\t Training accuracy: {results['accuracy']}")
            print(f"\t Test accuracy: {results['test_accuracy']}")
        return results

    def update_search_stats(self, results, run):
        self.accuracy_per_run[run] = results['accuracy']
        self.val_accuracy_per_run[run] = results['test_accuracy']
        self.performance_per_run[run] = results['best_performance']
        self.correlation_per_run[run] = results['correlation']
        self.outputs_per_run[run] = results['best_output']  # [:, 0]
        self.control_voltages_per_run[run] = 0  # results['control_voltages']
        self.seeds_per_run = results['seed']

    def update_best_run(self, results, run):
        results['index'] = run
        self.best_model = results['processor']
        self.best_run = results
        self.task.save_reproducibility_data(results)

    def close_search(self, gap):
        if self.configs['ring_data']['generate_data']:
            np.savez(os.path.join(self.search_stats_dir, f"search_data_{self.configs['runs']}_runs.npz"), outputs=self.outputs_per_run, performance=self.performance_per_run, correlation=self.correlation_per_run, accuracy=self.accuracy_per_run, seed=self.seeds_per_run, control_voltages=self.control_voltages_per_run)
        else:
            inputs_test, targets_test, mask_test = self.data_loader.get_data(self.configs['algorithm_configs']['processor'], gap=gap, istest=True)
            np.savez(os.path.join(self.search_stats_dir, f"search_data_{self.configs['runs']}_runs.npz"), outputs=self.outputs_per_run, performance=self.performance_per_run, correlation=self.correlation_per_run, accuracy=self.accuracy_per_run, test_accuracy=self.val_accuracy_per_run, seed=self.seeds_per_run, control_voltages=self.control_voltages_per_run, inputs_test=inputs_test, targets_test=targets_test, mask_test=mask_test)
        self.plot_search_results()

    def plot_search_results(self, extension='png'):
        best_index = self.best_run['index']
        performance = self.best_run["best_performance"]
        print(f"Best performance {performance} in run {best_index} with corr. {self.correlation_per_run[best_index]}")

        plt.figure()
        plt.plot(self.correlation_per_run, self.performance_per_run, 'o')
        plt.title('Correlation vs Fisher')
        plt.xlabel('Correlation')
        plt.ylabel('Fisher value')
        plt.savefig(os.path.join(self.search_stats_dir, 'correlation_vs_fisher.' + extension))
        plt.close()

        plt.figure()
        plt.plot(self.accuracy_per_run, self.performance_per_run, 'o')
        plt.title('Train accuracy vs Fisher')
        plt.xlabel('Accuracy')
        plt.ylabel('Fisher value')
        plt.savefig(os.path.join(self.search_stats_dir, 'train_accuracy_vs_fisher.' + extension))
        plt.close()

        plt.figure()
        plt.plot(self.val_accuracy_per_run, self.performance_per_run, 'o')
        plt.title('Test accuracy vs Fisher')
        plt.xlabel('Accuracy')
        plt.ylabel('Fisher value')
        plt.savefig(os.path.join(self.search_stats_dir, 'test_accuracy_vs_fisher.' + extension))
        plt.close()

        plt.figure()
        plt.hist(self.performance_per_run, 100)
        plt.title('Histogram of Fisher values')
        plt.xlabel('Fisher values')
        plt.ylabel('Counts')
        plt.savefig(os.path.join(self.search_stats_dir, 'fisher_values_histogram.' + extension))
        plt.close()

        plt.figure()
        plt.hist(self.accuracy_per_run, 100)
        plt.title('Histogram of Train Accuracy values')
        plt.xlabel('Accuracy values')
        plt.ylabel('Counts')
        plt.savefig(os.path.join(self.search_stats_dir, 'train_accuracy_histogram.' + extension))
        plt.close()

        plt.figure()
        plt.hist(self.val_accuracy_per_run, 100)
        plt.title('Histogram of Test Accuracy values')
        plt.xlabel('Accuracy values')
        plt.ylabel('Counts')
        plt.savefig(os.path.join(self.search_stats_dir, 'test_accuracy_histogram.' + extension))
        plt.close()

        plt.figure()
        index = np.argsort(self.accuracy_per_run)
        i_max = np.argmax(self.val_accuracy_per_run)
        plt.plot(self.accuracy_per_run[index], 'o--', label='train accuracy')
        plt.plot(self.val_accuracy_per_run[index], 'o--', label='test accuracy')
        plt.legend()
        plt.title(f'Sorted Train vs Test Accuracy \n Train: {self.accuracy_per_run[i_max]} Test: {self.val_accuracy_per_run[i_max]}')
        plt.xlabel('Run')
        plt.ylabel('Accuracy (%)')
        plt.savefig(os.path.join(self.search_stats_dir, 'train_vs_test_accuracy.' + extension))
        plt.close()

        plt.figure()
        index = np.argsort(self.performance_per_run)
        i_max = np.argmax(self.performance_per_run)
        plt.plot(self.performance_per_run[index], 'o--', label='fisher value')
        plt.plot(self.accuracy_per_run[index], 'o--', label='train accuracy')
        plt.plot(self.val_accuracy_per_run[index], 'o--', label='test accuracy')
        plt.legend()
        plt.title(f'Fisher vs Accuracy \n Train: {self.accuracy_per_run[i_max]} Test: {self.val_accuracy_per_run[i_max]}')
        plt.xlabel('Run')
        plt.ylabel('Accuracy (%) / fisher value')
        plt.savefig(os.path.join(self.search_stats_dir, 'fisher_vs_test_train_accuracy.' + extension))
        plt.close()

        if self.configs["show_plots"]:
            plt.show()


if __name__ == '__main__':
    import pandas as pd
    import torch
    import matplotlib.pyplot as plt
    from bspyalgo.utils.io import load_configs
    from bspyproc.utils.pytorch import TorchUtils

    TorchUtils.force_cpu = True

    # configs = load_configs('configs/tasks/ring/template_gd_architecture_cdaq_to_nidaq_validation2.json')
    configs = load_configs('configs/tasks/ring/template_gd_multiple_darwin_2.json')
    # configs = load_configs('configs/tasks/ring/template_gd_nn.json')
    searcher = RingSearcher(configs)
    searcher.search_solution(0.00625)