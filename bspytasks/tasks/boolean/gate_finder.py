
import numpy as np
import matplotlib.pyplot as plt
from bspyalgo.utils.performance import perceptron, corr_coeff
from bspyproc.utils.pytorch import TorchUtils
from bspyalgo.algorithm_manager import get_algorithm


class BooleanGateTask():

    def __init__(self, configs):
        self.algorithm = get_algorithm(configs)
        if configs['algorithm'] == 'gradient_descent' and configs['processor']['platform'] == 'simulation':
            self.find_label_core = self.find_label_with_torch
            self.ignore_label = self.ignore_label_with_torch
        else:
            self.find_label_core = self.find_label_with_numpy
            self.ignore_label = self.ignore_label_with_numpy

    def find_label(self, encoded_inputs, label, encoded_label, mask, threshold):
        if len(np.unique(label)) == 1:
            print('Label ', label, ' ignored')
            excel_results = self.ignore_label(encoded_label)
        else:
            excel_results = self.find_label_core(encoded_inputs, encoded_label, mask)
            excel_results['found'] = excel_results['accuracy'] >= threshold

        excel_results['label'] = label

        return excel_results

    def find_label_with_numpy(self, encoded_inputs, encoded_label, mask):
        excel_results = self.optimize(encoded_inputs, encoded_label, mask)
        excel_results['accuracy'], _, _ = perceptron(excel_results['best_output'][excel_results['mask']], encoded_label[excel_results['mask']])
        excel_results['encoded_label'] = encoded_label
        return excel_results

    def find_label_with_torch(self, encoded_inputs, encoded_label, mask):
        encoded_label = TorchUtils.format_tensor(encoded_label)
        excel_results = self.optimize(encoded_inputs, encoded_label, mask)
        excel_results['accuracy'], _, _ = perceptron(excel_results['best_output'][excel_results['mask']], TorchUtils.get_numpy_from_tensor(encoded_label[excel_results['mask']]))
        excel_results['encoded_label'] = encoded_label.cpu()
        # excel_results['targets'] = excel_results
        excel_results['correlation'] = corr_coeff(excel_results['best_output'][excel_results['mask']].T, excel_results['targets'].cpu()[excel_results['mask']].T)
        return excel_results

    def ignore_label_with_torch(self, encoded_label):
        excel_results = self.ignore_label_core()
        excel_results['encoded_label'] = encoded_label.cpu()
        return excel_results

    def ignore_label_with_numpy(self, encoded_label):
        excel_results = self.ignore_label_core()
        excel_results['encoded_label'] = encoded_label
        return excel_results

    def ignore_label_core(self):
        excel_results = {}
        excel_results['control_voltages'] = np.nan
        excel_results['best_output'] = np.nan
        excel_results['best_performance'] = np.nan
        excel_results['accuracy'] = np.nan
        excel_results['correlation'] = np.nan
        excel_results['found'] = True
        return excel_results

    def optimize(self, encoded_inputs, encoded_label, mask):
        algorithm_data = self.algorithm.optimize(encoded_inputs, encoded_label, mask=mask)
        algorithm_data.judge()
        excel_results = algorithm_data.results

        return excel_results

    def plot_gate(self, row, mask, show_plots, save_dir=None):
        plt.figure()
        plt.plot(row['best_output'][mask])
        plt.plot(row['encoded_label'][mask])
        plt.xlabel('Current (nA)')
        plt.ylabel('Time')
        if save_dir is not None:
            plt.savefig(save_dir)
        if show_plots:
            plt.show()


if __name__ == '__main__':
    from bspyalgo.utils.io import load_configs
    configs = load_configs('configs/tasks/boolean_gate/template_ga.json')

    # input_range = [[0, 0], [0, 1], [1, 0], [1, 1]]
    # input_range_in_voltage = [[-1.2, -1.2], [-1.2, 0.6], [0.6, -1.2], [0.6, 0.6]]
    # xor_target = [0, 1, 1, 0]

    test = BooleanGateTask(configs)
    test.find_label(input_range_in_voltage)
