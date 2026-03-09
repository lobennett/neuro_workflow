#!/bin/bash
#SBATCH --job-name=make_network
#SBATCH --output=make_network_%j.out
#SBATCH --error=make_network_%j.err
#SBATCH --time=2-00:00:00
#SBATCH -p russpold,hns,normal
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G

# Run using uv and specify the venv directory directly
module load uv

current_dir="$(pwd)"
network_script="/home/users/logben/fmri-outlier-detector/run_network.py"
discovery_dir="/oak/stanford/groups/russpold/data/network_grant/discovery_BIDS_20250402/derivatives/dataset-networkDiscovery_model-lev1_space-MNI_withinMaskThreshold-1.0_rtmodel-RTDur"
validation_dir="/oak/stanford/groups/russpold/data/network_grant/validation_BIDS/derivatives/dataset-networkValidation_model-lev1_space-MNI_withinMaskThreshold-1.0_rtmodel-RTDur"
output_dir="/scratch/users/logben/combined_network_analysis"
exclusions_file="/home/users/logben/network_glm/data/exclusions.json"

mkdir -p $output_dir
echo "Running analysis with both discovery and validation datasets..."
uv run --directory $current_dir python $network_script \
    --base_dirs $discovery_dir $validation_dir \
    --output_dir $output_dir \
    --exclusions-file $exclusions_file
