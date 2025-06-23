def transform_words_file(input_file, output_file):
    with open(input_file, 'r') as infile, open(output_file, 'w') as outfile:
        for line in infile:
            # Skip comments and empty lines
            if line.startswith('#') or not line.strip():
                continue
            
            # Split the line into components
            parts = line.strip().split()
            
            # Check if the line has enough parts to process
            if len(parts) >= 8:
                # Extract required fields
                key = parts[0]  # word id
                box = ' '.join(parts[4:8])  # bounding box (x, y, w, h)
                text = parts[-1]  # transcription
                
                # Write to output file
                outfile.write(f"{key} {box} {text}\n")

# Example usage
if __name__ == "__main__":
    input_file = "./train_data/iamdb/words.txt"
    output_file = "./train_data/words_new.txt"
    transform_words_file(input_file, output_file)