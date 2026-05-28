"""
Convert CSV data to JSONL format for Cypher generation fine-tuning.
This script processes the results.csv file and creates train/test splits.
"""

import csv
import json
import random
import os


def create_cypher_training_data(
    csv_path: str = "results.csv",
    output_dir: str = "/tmp/tinker-datasets",
    train_file: str = "cypher_train.jsonl",
    test_file: str = "cypher_test.jsonl",
    train_size: int = 250,
    random_seed: int = 42,
):
    """
    Convert CSV with question/cypher pairs to JSONL format for training.

    Args:
        csv_path: Path to input CSV file
        output_dir: Directory to save output files
        train_file: Name of training JSONL file
        test_file: Name of test JSONL file
        train_size: Number of samples for training (rest goes to test)
        random_seed: Random seed for reproducibility
    """
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # Read CSV
    print(f"Reading data from {csv_path}...")
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        data = list(reader)

    print(f"Total samples: {len(data)}")

    # Shuffle with fixed seed
    random.seed(random_seed)
    random.shuffle(data)

    # Split
    train_data = data[:train_size]
    test_data = data[train_size:]

    print(f"Training samples: {len(train_data)}")
    print(f"Test samples: {len(test_data)}")

    # Convert to JSONL format
    train_path = os.path.join(output_dir, train_file)
    test_path = os.path.join(output_dir, test_file)

    print(f"\nWriting training data to {train_path}...")
    with open(train_path, 'w') as f:
        for row in train_data:
            # Clean the cypher query (remove extra quotes if present)
            cypher = row['cypher_query'].strip('"')

            message_obj = {
                "messages": [
                    {
                        "role": "user",
                        "content": row['question']
                    },
                    {
                        "role": "assistant",
                        "content": cypher
                    }
                ]
            }
            f.write(json.dumps(message_obj) + '\n')

    print(f"Writing test data to {test_path}...")
    with open(test_path, 'w') as f:
        for row in test_data:
            cypher = row['cypher_query'].strip('"')

            message_obj = {
                "messages": [
                    {
                        "role": "user",
                        "content": row['question']
                    },
                    {
                        "role": "assistant",
                        "content": cypher
                    }
                ]
            }
            f.write(json.dumps(message_obj) + '\n')

    print("\n✅ Data conversion complete!")
    print(f"   Training: {train_path} ({len(train_data)} samples)")
    print(f"   Test: {test_path} ({len(test_data)} samples)")

    # Show a sample
    print("\n📝 Sample training example:")
    print(f"   Question: {train_data[0]['question']}")
    print(f"   Cypher: {train_data[0]['cypher_query'].strip('\"')[:100]}...")

    return train_path, test_path


if __name__ == "__main__":
    create_cypher_training_data()
