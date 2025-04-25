import matplotlib.pyplot as plt
import ast # To safely evaluate the string representation of the dictionary

def parse_log_file(log_file_path):
    """Parses the training log file."""
    data = []
    try:
        with open(log_file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line: # Make sure the line is not empty
                    try:
                        # Safely evaluate the string as a Python literal (dictionary)
                        log_entry = ast.literal_eval(line)
                        if isinstance(log_entry, dict):
                            data.append(log_entry)
                        else:
                            print(f"Warning: Skipped line not evaluating to a dict: {line}")
                    except (ValueError, SyntaxError) as e:
                        print(f"Warning: Could not parse line: {line}\nError: {e}")
    except FileNotFoundError:
        print(f"Error: Log file not found at {log_file_path}")
        return None
    return data

def plot_training_progress(data, save_path=None):
    """Plots loss, grad_norm, and learning_rate against epoch."""
    if not data:
        print("No data to plot.")
        return

    # Extract data for plotting
    epochs = [item.get('epoch', None) for item in data]
    losses = [item.get('loss', None) for item in data]
    grad_norms = [item.get('grad_norm', None) for item in data]
    learning_rates = [item.get('learning_rate', None) for item in data]

    # Filter out entries where epoch might be missing (though unlikely based on your format)
    valid_indices = [i for i, e in enumerate(epochs) if e is not None]
    if not valid_indices:
        print("No valid epoch data found.")
        return

    epochs = [epochs[i] for i in valid_indices]
    losses = [losses[i] for i in valid_indices]
    grad_norms = [grad_norms[i] for i in valid_indices]
    learning_rates = [learning_rates[i] for i in valid_indices]

    # Create subplots (3 rows, 1 column), sharing the x-axis
    fig, axs = plt.subplots(3, 1, figsize=(10, 12), sharex=True)

    # Plot Loss
    axs[0].plot(epochs, losses, marker='o', linestyle='-', label='Loss')
    axs[0].set_ylabel('Loss')
    axs[0].set_title('Training Loss')
    axs[0].grid(True)
    axs[0].legend()

    # Plot Gradient Norm
    axs[1].plot(epochs, grad_norms, marker='o', linestyle='-', color='orange', label='Gradient Norm')
    axs[1].set_ylabel('Gradient Norm')
    axs[1].set_title('Gradient Norm')
    axs[1].grid(True)
    axs[1].legend()

    # Plot Learning Rate
    axs[2].plot(epochs, learning_rates, marker='o', linestyle='-', color='green', label='Learning Rate')
    axs[2].set_ylabel('Learning Rate')
    axs[2].set_xlabel('Epoch')
    axs[2].set_title('Learning Rate Schedule')
    axs[2].ticklabel_format(style='sci', axis='y', scilimits=(0,0)) # Use scientific notation for LR
    axs[2].grid(True)
    axs[2].legend()

    # Overall title and layout adjustment
    fig.suptitle('Training Progress Visualization', fontsize=16)
    plt.tight_layout(rect=[0, 0.03, 1, 0.97]) # Adjust layout to prevent title overlap

    # Save the plot if a path is provided
    if save_path:
        try:
            plt.savefig(save_path)
            print(f"Plot saved to {save_path}")
        except Exception as e:
            print(f"Error saving plot: {e}")

    # Show the plot
    plt.show()

# --- Main Execution ---
if __name__ == "__main__":
    log_file = 'training_log.txt'  # Make sure this file exists and contains your log data
    parsed_data = parse_log_file(log_file)

    if parsed_data:
        # You can optionally save the plot to a file, e.g., 'training_plot.png'
        plot_training_progress(parsed_data, save_path='training_plot.png')
        # plot_training_progress(parsed_data) # Or just display it without saving
