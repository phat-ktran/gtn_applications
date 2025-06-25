import random
from typing import Set, List
import os

def extract_document_ids(file_path: str) -> Set[str]:
    """Extract unique document IDs from the words.txt file."""
    doc_ids = set()
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                # Extract document ID (e.g., 'a01-000u' from 'a01-000u-00-00')
                doc_id = line.split()[0]
                doc_ids.add(doc_id)
    return doc_ids

def split_train_val(doc_ids: List[str], train_ratio: float = 0.8) -> tuple[List[str], List[str]]:
    """Split document IDs into train and validation sets."""
    random.seed(42)  # For reproducibility
    random.shuffle(doc_ids)
    train_size = int(len(doc_ids) * train_ratio)
    train_ids = doc_ids[:train_size]
    val_ids = doc_ids[train_size:]
    return train_ids, val_ids

def write_id_files(train_ids: List[str], val_ids: List[str], output_dir: str):
    """Write train and validation IDs to separate text files."""
    os.makedirs(output_dir, exist_ok=True)
    
    with open(os.path.join(output_dir, 'train.txt'), 'w', encoding='utf-8') as f:
        for doc_id in sorted(train_ids):
            f.write(f"{doc_id}\n")
    
    with open(os.path.join(output_dir, 'val.txt'), 'w', encoding='utf-8') as f:
        for doc_id in sorted(val_ids):
            f.write(f"{doc_id}\n")

def main():
    # Input file path
    input_file = './train_data/iamdb/words.txt'
    # Output directory for train/val ID files
    output_dir = './train_data/'
    
    # Extract unique document IDs
    doc_ids = list(extract_document_ids(input_file))
    print(f"Found {len(doc_ids)} unique document IDs")
    
    # Split into train and validation
    train_ids, val_ids = split_train_val(doc_ids)
    print(f"Train set: {len(train_ids)} IDs")
    print(f"Validation set: {len(val_ids)} IDs")
    
    # Write IDs to files
    write_id_files(train_ids, val_ids, output_dir)
    print(f"Train and validation ID files written to {output_dir}")

if __name__ == "__main__":
    main()