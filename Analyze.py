import os
import json
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import torch
import numpy as np
import argparse
from scipy import linalg
import torchvision.models as models
from torchvision.models import Inception_V3_Weights
import torchvision.transforms as transforms
from PIL import Image

class FIDCalculator:
    def __init__(self, device='cuda' if torch.cuda.is_available() else 'cpu'):
        """
        Initialize FID calculator with pretrained Inception v3 model
        
        Args:
            device (str): Computation device
        """        
        # Load pretrained Inception v3 model
        self.inception_model = models.inception_v3(weights=Inception_V3_Weights.DEFAULT)
        self.inception_model.fc = torch.nn.Identity()  # Remove classification layer
        self.inception_model.eval()
        self.inception_model = self.inception_model.to(device)
        
        self.device = device
        
        # Transformation for image loading
        self.transform = transforms.Compose([
            transforms.Resize((299, 299)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])
    
    def _compute_statistics(self, images):
        """
        Compute mean and covariance of image features
        
        Args:
            images (torch.Tensor): Batch of images
        
        Returns:
            tuple: Mean and covariance of image features
        """
        try:
            # Compute features
            with torch.no_grad():
                features = self.inception_model(images)
            
            # Convert to numpy 
            features_np = features.cpu().numpy()
            
            # If only one image, we can't compute meaningful covariance
            if features_np.shape[0] == 1:
                print("Warning: Only one image provided. Cannot compute meaningful FID.")
                return None, None
            
            # Compute statistics
            mu = np.mean(features_np, axis=0)
            sigma = np.cov(features_np, rowvar=False)
            
            return mu, sigma
        
        except Exception as e:
            print(f"Detailed error in feature extraction: {e}")
            import traceback
            traceback.print_exc()
            return None, None
    
    def calculate_fid(self, real_images, generated_images):
        """
        Calculate Frechet Inception Distance between two image sets
        
        Args:
            real_images (torch.Tensor): Batch of real/clean images
            generated_images (torch.Tensor): Batch of generated/denoised images
        
        Returns:
            float: FID score or float('inf') if calculation fails
        """
        # Ensure images are on the right device
        real_images = real_images.to(self.device)
        generated_images = generated_images.to(self.device)
        
        # Compute statistics with error handling
        mu1, sigma1 = self._compute_statistics(real_images)
        mu2, sigma2 = self._compute_statistics(generated_images)
        
        # Check if we have valid statistics
        if mu1 is None or sigma1 is None or mu2 is None or sigma2 is None:
            print("Failed to compute valid statistics for images")
            return float('inf')
        
        # Compute squared difference of means
        diff = mu1 - mu2
        
        try:
            # Add small regularization term to avoid numerical instability
            sigma1 = sigma1 + np.eye(sigma1.shape[0]) * 1e-6
            sigma2 = sigma2 + np.eye(sigma2.shape[0]) * 1e-6
            
            # Compute matrix square root
            covmean = linalg.sqrtm(sigma1.dot(sigma2))
            
            # Handle potential complex numbers
            if np.iscomplexobj(covmean):
                covmean = covmean.real
            
            # Calculate FID
            fid = (diff.dot(diff) + 
                np.trace(sigma1 + sigma2 - 2 * covmean))
            
            return fid
        
        except Exception as e:
            print(f"Error in FID calculation: {e}")
            return float('inf')
    
    def load_and_preprocess_images(self, original_path, generated_path):
        """
        Load and preprocess images for FID calculation
        
        Args:
            original_path (str): Path to original image
            generated_path (str): Path to generated image
        
        Returns:
            tuple: Preprocessed original and generated image tensors
        """
        try:
            # Load images
            original_img = Image.open(original_path).convert('RGB')
            generated_img = Image.open(generated_path).convert('RGB')
            
            # Preprocess images
            original_tensor = self.transform(original_img).unsqueeze(0)
            generated_tensor = self.transform(generated_img).unsqueeze(0)
            
            return original_tensor, generated_tensor
        except Exception as e:
            print(f"Error loading images: {e}")
            return None, None
        
def load_experiment_results(experiment_path):
    """
    Load results from JSON and CSV files in an experiment folder
    
    Args:
        experiment_path (str): Path to experiment folder
    
    Returns:
        dict: Loaded results
    """
    results = {}
    
    # Try to load JSON results
    json_path = os.path.join(experiment_path, 'results.json')
    if os.path.exists(json_path):
        with open(json_path, 'r') as f:
            results = json.load(f)
    
    # Check for CSV files
    csv_path = os.path.join(experiment_path, 'epoch_data.csv')
    if os.path.exists(csv_path):
        results['epoch_data'] = pd.read_csv(csv_path)
    
    return results

def create_epoch_plots(results, experiment_path):
    """
    Create plots for training, validation, and test metrics
    
    Args:
        results (dict): Experiment results
        experiment_path (str): Path to experiment folder
    """    
    # Check if epoch data exists
    if 'epoch_data' not in results:
        print(f"No epoch data found for {experiment_path}")
        return
    
    df = results['epoch_data']
    
    plt.figure(figsize=(15, 6))
    
    # Loss Subplot
    plt.subplot(1, 3, 1)
    plt.title('Loss per Epoch')
    plt.plot(df['Epoch'], df['Train Loss'], label='Train Loss')
    plt.plot(df['Epoch'], df['Validation Loss'], label='Validation Loss')
    plt.xlabel('Epoch')
    plt.ylabel('Loss')
    plt.legend()
    
    # Accuracy Subplot
    plt.subplot(1, 3, 2)
    plt.title('Accuracy per Epoch')
    plt.plot(df['Epoch'], df['Train Accuracy'], label='Train Accuracy')
    plt.plot(df['Epoch'], df['Validation Accuracy'], label='Validation Accuracy')
    plt.xlabel('Epoch')
    plt.ylabel('Accuracy')
    plt.legend()
    
    # Metrics Comparison Subplot
    plt.subplot(1, 3, 3)
    metrics = {
        'Test Loss': results.get('test_loss', 0),
        'Test Accuracy': results.get('test_accuracy', 0)
    }
    
    # Create bar plot
    bars = plt.bar(list(metrics.keys()), list(metrics.values()))
    plt.title('Final Metrics')
    plt.xticks(rotation=45, ha='right')
    plt.ylabel('Value')
    
    # Add value annotations
    for bar in bars:
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2., height, 
                    f'{height:.4f}', 
                    ha='center', va='bottom')
    
    plt.tight_layout()
    
    # Add computation time as text at the bottom
    computation_time = results.get('computation_time', 0)
    plt.figtext(0.5, 0.01, 
        f'Computation Time: {int(computation_time // 3600)} Hrs {int((computation_time % 3600) // 60)} Min {int(computation_time % 60)} Sec', 
        ha='center', fontsize=10, bbox=dict(facecolor='white', alpha=0.5))
    
    # Save the plot
    plot_path = os.path.join(experiment_path, 'epoch_analysis.png')
    plt.savefig(plot_path, bbox_inches='tight', dpi=300)
    
    plt.close()

def calculate_fid_for_experiments(results_dir, dataset):
    """
    Calculate FID for all experiments by batching all original and generated images
    
    Args:
        results_dir (str): Directory containing experiment results
        dataset (str): Dataset to filter experiments by
    
    Returns:
        list: FID calculation results
    """    
    experiments = [d for d in os.listdir(results_dir) 
                   if os.path.isdir(os.path.join(results_dir, d)) and d != f'!Compare_All_{dataset.lower()}']
    
    # Filter experiments by dataset
    if dataset:
        experiments = [exp for exp in experiments if exp.lower().endswith('_' + dataset.lower())]
    
    # Prepare FID results
    fid_results = []
    
    # Initialize FID calculator
    fid_calculator = FIDCalculator()
    
    for experiment in experiments:
        exp_path = os.path.join(results_dir, experiment)
        
        # Path to images folder
        images_path = os.path.join(exp_path, 'images')
        
        # If images folder doesn't exist, skip
        if not os.path.exists(images_path):
            print(f"No images folder found for experiment: {experiment}")
            continue
        
        # Lists to store all original and generated images
        all_original_images = []
        all_generated_images = []
        
        for filename in os.listdir(images_path):
            if filename.endswith('_original.png'):
                base_name = filename[:-13]
                original_path = os.path.join(images_path, filename)
                generated_path = os.path.join(images_path, f"{base_name}_generated.png")
                
                if os.path.exists(generated_path):
                    try:
                        # Load and preprocess individual images
                        original_tensor, generated_tensor = fid_calculator.load_and_preprocess_images(
                            original_path, generated_path
                        )
                        
                        if original_tensor is not None and generated_tensor is not None:
                            all_original_images.append(original_tensor)
                            all_generated_images.append(generated_tensor)
                    
                    except Exception as e:
                        print(f"Error processing {original_path} and {generated_path}: {e}")
        
        # Validate image sets
        if len(all_original_images) == 0:
            print(f"No images found for experiment: {experiment}")
            continue
        
        # Stack all images into a single tensor
        try:
            original_batch = torch.cat(all_original_images, dim=0)
            generated_batch = torch.cat(all_generated_images, dim=0)
            
            # Compute FID for the entire batch
            fid_score = fid_calculator.calculate_fid(original_batch, generated_batch)
            
            # Store results
            fid_results.append({
                'Experiment': experiment,
                'FID Score': fid_score,
                'Number of Images': len(all_original_images)
            })
        
        except Exception as e:
            print(f"Error computing FID for experiment {experiment}: {e}")
    
    # Ensure dataset-specific !Compare_All directory exists
    compare_all_path = os.path.join(results_dir, f'!Compare_All_{dataset.lower()}')
    os.makedirs(compare_all_path, exist_ok=True)
    
    # Save FID results to CSV
    fid_csv_path = os.path.join(compare_all_path, f'fid_scores_{dataset.lower()}.csv')
    
    fid_df = pd.DataFrame(fid_results)
    fid_df.to_csv(fid_csv_path, index=False)
    
    return fid_results

def compare_all_experiments(comparison_data, fid_results, results_dir, dataset):
    """
    Create a comprehensive comparison of all experiments
    Saves results in a dataset-specific directory
    
    Args:
        comparison_data (list): List of experiment metrics
        fid_results (list): List of FID calculation results
        results_dir (str): Directory containing experiment results
        dataset (str): Dataset to filter experiments by
    """
    # Ensure dataset-specific !Compare_All directory exists
    compare_all_path = os.path.join(results_dir, f'!Compare_All_{dataset.lower()}')
    os.makedirs(compare_all_path, exist_ok=True)
    
    # Create comparison DataFrame
    comparison_df = pd.DataFrame(comparison_data)
    
    # Clean experiment names by removing dataset suffix and formatting
    dataset_suffix = f'_{dataset.lower()}'
    comparison_df['CleanName'] = comparison_df['Experiment'].apply(
        lambda x: ' '.join(word.capitalize() for word in x.replace(dataset_suffix, '').split('_'))
    )
    
    # Create FID DataFrame
    fid_df = pd.DataFrame(fid_results)
    
    # Add FID information to comparison DataFrame
    if not fid_df.empty and 'Experiment' in fid_df.columns:
        comparison_df['FID Score'] = comparison_df['Experiment'].map(
            dict(zip(fid_df['Experiment'], fid_df['FID Score']))
        )
    else:
        print("Warning: No FID data available or 'Experiment' column missing")
        comparison_df['FID Score'] = np.nan
    
    # Plotting individual metrics
    metrics = ['Test Loss', 'Test Accuracy', 'Computation Time', 'FID Score']
    
    # For certain metrics, lower is better
    lower_is_better = {'Test Loss': True, 'Computation Time': True, 'FID Score': True}
    
    for metric in metrics:
        plt.figure(figsize=(10, 6))
        
        # Determine top 3 experiments based on metric
        if metric in lower_is_better and lower_is_better[metric]:
            top_indices = comparison_df[metric].nsmallest(3).index
        else:
            top_indices = comparison_df[metric].nlargest(3).index
        
        # Create a list of colors for the bars
        colors = ['#1f77b4'] * len(comparison_df)  # Default blue color
        for idx in top_indices:
            colors[idx] = '#2ca02c'  # Green color for top performers
        
        # Create bar plot with cleaned names and custom colors
        bars = plt.bar(comparison_df['CleanName'], comparison_df[metric], color=colors)
        
        plt.title(f'{metric} Comparison for {dataset}')
        fig_path = os.path.join(compare_all_path, f'{metric.lower().replace(" ", "_")}_comparison_{dataset.lower()}.png')
        
        plt.xticks(rotation=45, ha='right')
        plt.xlabel('Experiment Type')
        plt.ylabel(metric)
        
        # Add value annotations
        for bar in bars:
            height = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2., height, 
                    f'{height:.4f}', 
                    ha='center', va='bottom')
        
        # Add a legend indicating green bars are best 3 performers
        from matplotlib.patches import Patch
        legend_elements = [Patch(facecolor='#2ca02c', label='Best 3')]
        plt.legend(handles=legend_elements)
        
        plt.tight_layout()
        plt.savefig(fig_path)
        plt.close()
    
    # Save comparison data with clean names
    csv_path = os.path.join(compare_all_path, f'experiments_comparison_{dataset.lower()}.csv')
    comparison_df.to_csv(csv_path, index=False)

def main():
    """
    Analyze results for all experiments
    """
    # Add argument parsing
    parser = argparse.ArgumentParser(description='Analyze experiment results')
    parser.add_argument('--noise', type=str, default='all',
                      help='Noise level for results directory (choices: 0.15, 0.25, 0.5, all) (default: all)')
    parser.add_argument('--dataset', type=str, default='all',
                     help='Dataset to use (choices: MNIST, CIFAR10, CIFAR100, STL10, all) (default: all)')
    args = parser.parse_args()
    
    # Define available noise levels and datasets
    noise_levels = [0.15, 0.25, 0.5]
    datasets = ['MNIST', 'CIFAR10', 'CIFAR100', 'STL10']
    
    # Determine which noise levels to process
    if args.noise.lower() == 'all':
        noise_to_process = noise_levels
    else:
        try:
            noise_value = float(args.noise)
            if noise_value in noise_levels:
                noise_to_process = [noise_value]
            else:
                print(f"Invalid noise value: {args.noise}. Using default 'all'.")
                noise_to_process = noise_levels
        except ValueError:
            print(f"Invalid noise value: {args.noise}. Using default 'all'.")
            noise_to_process = noise_levels
    
    # Determine which datasets to process
    if args.dataset.lower() == 'all':
        datasets_to_process = datasets
    elif args.dataset in datasets:
        datasets_to_process = [args.dataset]
    else:
        print(f"Invalid dataset: {args.dataset}. Using default 'all'.")
        datasets_to_process = datasets
    
    # Process each noise level (using specific float values, never "all")
    for noise in noise_to_process:  # noise is always a float value from noise_levels
        results_dir = f'Results_{noise}'
        print(f"{'='*75}")
        print(f"\tUsing results directory: {results_dir}")
        
        # Ensure results directory exists
        os.makedirs(results_dir, exist_ok=True)
        
        # Process each dataset (using specific dataset names, never "all")
        for dataset in datasets_to_process:  # dataset is always a string from datasets
            print(f"{'='*75}")
            print(f"\tPROCESSING NOISE LEVEL: {noise}\t\tDATASET: {dataset}")
            print(f"{'='*75}")
            
            # Prepare data for comparison
            comparison_data = []
            
            # Process each experiment
            print(f"Loading experiment data and creating epoch plots for {dataset}...\n")
            for experiment in os.listdir(results_dir):
                experiment_path = os.path.join(results_dir, experiment)
                
                # Skip if not a directory or is !Compare_All
                if not os.path.isdir(experiment_path) or experiment == '!Compare_All':
                    continue
                
                # Skip if doesn't match dataset filter
                if not experiment.lower().endswith('_' + dataset.lower()):
                    continue
                
                # Load results
                results = load_experiment_results(experiment_path)
                
                # Skip if no results found
                if not results:
                    continue
                
                # Create plots
                create_epoch_plots(results, experiment_path)
                
                # Add to comparison data
                comparison_data.append({
                    'Experiment': experiment,
                    'Test Loss': results.get('test_loss', 0),
                    'Test Accuracy': results.get('test_accuracy', 0),
                    'Computation Time': results.get('computation_time', 0)
                })
            
            # Calculate FID for experiments using specific dataset name
            print(f"Calculating FID results for {dataset}...\n")
            fid_results = calculate_fid_for_experiments(results_dir, dataset)  # Using specific dataset name
            
            # Create comprehensive comparison using specific dataset name
            print(f"Comparing all experiments for {dataset}...\n")
            compare_all_experiments(comparison_data, fid_results, results_dir, dataset)  # Using specific dataset name

if __name__ == "__main__":
    main()