"""
Copyright (c) Facebook, Inc. and its affiliates.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.
"""

import collections
import itertools
import multiprocessing as mp
import os
import PIL.Image
import random
import torch
from torchvision import transforms


SPLITS = {
    "train": ["train"],
    "validation": ["validate"],
    "test": ["validation"],
}


class Dataset(torch.utils.data.Dataset):
    def __init__(self, data_path, preprocessor, split, augment=False):
        forms = load_metadata(data_path, use_words=preprocessor.use_words)

        # Get split keys:
        splits = SPLITS.get(split, None)
        if splits is None:
            split_names = ", ".join(f"'{k}'" for k in SPLITS.keys())
            raise ValueError(f"Invalid split {split}, must be in [{split_names}].")

        split_keys = []
        for s in splits:
            with open(os.path.join(data_path, f"{s}.txt"), "r") as fid:
                split_keys.extend((l.strip() for l in fid))

        self.preprocessor = preprocessor

        # setup image transforms:
        self.transforms = []
        if augment:
            self.transforms.extend(
                [
                    RandomResizeCrop(),
                    transforms.RandomRotation(2, fill=(255,)),
                    transforms.ColorJitter(0.5, 0.5, 0.5, 0.5),
                ]
            )
        self.transforms.extend(
            [
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.912], std=[0.168]),
            ]
        )
        self.transforms = transforms.Compose(self.transforms)

        # Load each image:
        images = []
        text = []
        for key, examples in forms.items():
            for example in examples:
                if example["key"] not in split_keys:
                    continue
                images.append((example["path"], preprocessor.num_features))
                text.append(example["text"])
        with mp.Pool(processes=16) as pool:
            images = pool.map(load_image, images)
        self.dataset = list(zip(images, text))

    def sample_sizes(self):
        """
        Returns a list of tuples containing the input size
        (width, height) and the output length for each sample.
        """
        return [(image.size, len(text)) for image, text in self.dataset]

    def __getitem__(self, index):
        img, text = self.dataset[index]
        inputs = self.transforms(img)
        outputs = self.preprocessor.to_index(text)
        return inputs, outputs

    def __len__(self):
        return len(self.dataset)


def load_image(example):
    img_file, _ = example
    img = PIL.Image.open(img_file).convert("RGB")  # Ensure RGB mode
    width, height = img.size
    new_height = 64
    target_width = 880
    if height == 0:
        new_width = width
    else:
        aspect_ratio = float(width) / height
        new_width = int(aspect_ratio * new_height)
    if new_width >= target_width:
        img = img.resize((target_width, new_height), PIL.Image.Resampling.LANCZOS)
    else:
        img = img.resize((new_width, new_height), PIL.Image.Resampling.LANCZOS)
        padded_img = PIL.Image.new(
            "RGB", (target_width, new_height), color=(255, 255, 255)
        )
        padded_img.paste(img, (0, 0))
        img = padded_img
    img = img.convert("L")  # Convert to 1-channel grayscale
    return img


class RandomResizeCrop:
    def __init__(self, jitter=10, ratio=0.5):
        self.jitter = jitter
        self.ratio = ratio

    def __call__(self, img):
        w, h = img.size

        # pad with white:
        img = transforms.functional.pad(img, self.jitter, fill=255)

        # crop at random (x, y):
        x = self.jitter + random.randint(-self.jitter, self.jitter)
        y = self.jitter + random.randint(-self.jitter, self.jitter)

        # randomize aspect ratio:
        size_w = w * random.uniform(1 - self.ratio, 1 + self.ratio)
        size = (h, int(size_w))
        img = transforms.functional.resized_crop(img, y, x, h, w, size)
        return img


class Preprocessor:
    """
    A preprocessor for the IAMDB dataset.
    Args:
        data_path (str) : Path to the top level data directory.
        img_heigh (int) : Height to resize extracted images.
        tokens_path (str) (optional) : The path to the list of model output
            tokens. If not provided the token set is built dynamically from
            the graphemes of the tokenized text. NB: This argument does not
            affect the tokenization of the text, only the number of output
            classes.
        lexicon_path (str) (optional) : A mapping of words to tokens. If
            provided the preprocessor will split the text into words and
            map them to the corresponding token. If not provided the text
            will be tokenized at the grapheme level.
    """

    def __init__(
        self,
        data_path,
        num_features,
        tokens_path=None,
        lexicon_path=None,
        use_words=False,
        prepend_wordsep=False,
    ):
        self.wordsep = "▁"
        self._use_words = use_words
        self._prepend_wordsep = prepend_wordsep

        forms = load_metadata(data_path, use_words=use_words)

        # Load the set of graphemes:
        graphemes = set()
        for _, form in forms.items():
            for line in form:
                graphemes.update(line["text"])
        self.graphemes = sorted(graphemes)
        self.graphemes.insert(0, "BLANK")

        # Build the token-to-index and index-to-token maps:
        if tokens_path is not None:
            with open(tokens_path, "r") as fid:
                self.tokens = [l.strip() for l in fid]
        else:
            # Default to use graphemes if no tokens are provided
            self.tokens = self.graphemes

        if lexicon_path is not None:
            with open(lexicon_path, "r") as fid:
                lexicon = (l.strip().split() for l in fid)
                lexicon = {l[0]: l[1:] for l in lexicon}
                self.lexicon = lexicon
        else:
            self.lexicon = None
        self.graphemes_to_index = {t: i for i, t in enumerate(self.graphemes)}
        self.tokens_to_index = {t: i for i, t in enumerate(self.tokens)}
        self.num_features = num_features

    @property
    def num_tokens(self):
        return len(self.tokens)

    @property
    def use_words(self):
        return self._use_words

    def to_index(self, line):
        tok_to_idx = self.graphemes_to_index
        if self.lexicon is not None:
            if len(line) > 0:
                # If the word is not found in the lexicon, fall back to letters.
                line = [
                    t
                    for w in line.split(self.wordsep)
                    for t in self.lexicon.get(w, self.wordsep + w)
                ]
                tok_to_idx = self.tokens_to_index
        if self._prepend_wordsep:
            line = itertools.chain([self.wordsep], line)
        return torch.LongTensor([tok_to_idx[t] for t in line])

    def to_text(self, indices):
        # Roughly the inverse of `to_index`
        encoding = self.graphemes
        if self.lexicon is not None:
            encoding = self.tokens
        # Add safety check to prevent index out of bounds
        safe_indices = [i for i in indices if 0 <= i < len(encoding)]
        return self._post_process(encoding[i] for i in safe_indices)

    def tokens_to_text(self, indices):
        # Add safety check to prevent index out of bounds
        safe_indices = [i for i in indices if 0 <= i < len(self.tokens)]
        return self._post_process(self.tokens[i] for i in safe_indices)

    def _post_process(self, indices):
        # ignore preceding and trailling spaces
        return "".join(indices).strip(self.wordsep)


def load_metadata(data_path, use_words=False):
    forms = collections.defaultdict(list)
    filename = "nomna-all.txt"
    with open(os.path.join(data_path, filename), "r") as fid:
        for line in fid:
            parts = line.strip().split("\t")
            word_id = parts[0]
            text_label = parts[-1]  # The actual word is the last part
            path = os.path.join(data_path, word_id)
            form_key = word_id.split("/")[0]

            forms[form_key].append(
                {
                    "key": word_id,
                    "path": path,
                    "text": text_label,
                }
            )
    return forms


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Compute data stats.")
    parser.add_argument("--data_path", type=str, help="Path to dataset.")
    parser.add_argument(
        "--use_words",
        default=False,
        action="store_true",
        help="Load word segmented dataset instead of lines.",
    )
    parser.add_argument(
        "--save_text", type=str, help="Path to save parsed train text.", default=None
    )
    parser.add_argument(
        "--save_tokens", type=str, help="Path to save tokens.", default=None
    )
    parser.add_argument(
        "--compute_stats",
        action="store_true",
        help="Compute training data statistics.",
        default=False,
    )
    args = parser.parse_args()

    preprocessor = Preprocessor(args.data_path, 64, use_words=args.use_words)
    trainset = Dataset(args.data_path, preprocessor, split="train", augment=False)
    if args.save_text is not None:
        with open(args.save_text, "w") as fid:
            fid.write("\n".join(t for _, t in trainset.dataset))
    if args.save_tokens is not None:
        with open(args.save_tokens, "w") as fid:
            fid.write("\n".join(preprocessor.tokens))
    valset = Dataset(args.data_path, preprocessor, split="validation")
    print("Number of examples per dataset:")
    print(f"Training: {len(trainset)}")
    print(f"Validation: {len(valset)}")

    if not args.compute_stats:
        import sys

        print("here")
        sys.exit(0)

    # Compute mean and var stats:
    images = torch.cat([trainset[i][0] for i in range(len(trainset))], dim=2)
    mean = torch.mean(images)
    std = torch.std(images)
    print(f"Data mean {mean} and standard deviation {std}.")

    # Compute average lengths of images and targets:
    avg_im_w = sum(w for (w, _), _ in trainset.sample_sizes()) / len(trainset)
    avg_tgt_l = sum(l for _, l in trainset.sample_sizes()) / len(trainset)
    print(f"Average image width {avg_im_w}")
    print(f"Average target length {avg_tgt_l}")
