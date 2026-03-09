#!/bin/bash
#SBATCH --job-name=run_report
#SBATCH --output=run_report_%j.out
#SBATCH --error=run_report_%j.err
#SBATCH --time=02:00:00
#SBATCH -p russpold,hns,normal
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G

# Run using uv and specify the venv directory directly
current_dir="$(pwd)"
report_script="/home/users/logben/fmri-outlier-detector/run_report.py"

# COMBINED ANALYSIS (Discovery + Validation)
input_file="/scratch/users/logben/combined_network_analysis/percent_outlier_data.csv"
discovery_dir="/oak/stanford/groups/russpold/data/network_grant/discovery_BIDS_20250402/derivatives/dataset-networkDiscovery_model-lev1_space-MNI_withinMaskThreshold-1.0_rtmodel-RTDur/"
validation_dir="/oak/stanford/groups/russpold/data/network_grant/validation_BIDS/derivatives/dataset-networkValidation_model-lev1_space-MNI_withinMaskThreshold-1.0_rtmodel-RTDur/"
output_dir="/scratch/users/logben/combined_network_analysis/"

module load uv

mkdir -p $output_dir
echo "Running analysis to create combined report..."
echo "Using both discovery and validation directories for scan proportion calculations"
uv run --directory $current_dir python $report_script \
    --input-file $input_file \
    --output-dir $output_dir \
    --lev1-output $discovery_dir $validation_dir