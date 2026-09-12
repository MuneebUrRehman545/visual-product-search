"""
Create a sample product dataset from a large image catalog.

Example:
    python scripts/create_sample_dataset.py \
        --images-dir data/images \
        --metadata-file data/styles.csv \
        --output-dir data/catalog \
        --sample-size 2000 \
        --replace
"""

from __future__ import annotations

import argparse
import logging
import random
import shutil
import sys
from pathlib import Path

import pandas as pd
from PIL import Image


SUPPORTED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
}


def configure_logging() -> None:
    """Configure console logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )


def parse_arguments() -> argparse.Namespace:
    """Read command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Select a sample of products, copy their images, "
            "and export the matching metadata."
        )
    )

    parser.add_argument(
        "--images-dir",
        type=Path,
        default=Path("data/images"),
        help="Folder containing the complete image dataset.",
    )

    parser.add_argument(
        "--metadata-file",
        type=Path,
        default=Path("data/styles.csv"),
        help="Path to the metadata Excel or CSV file.",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/catalog"),
        help="Folder where the selected sample will be created.",
    )

    parser.add_argument(
        "--sample-size",
        "--catalog-size",
        type=int,
        default=2000,
        dest="sample_size",
        help="Number of products to select. Default: 2000.",
    )

    parser.add_argument(
        "--group-column",
        type=str,
        default="articleType",
        help="Metadata column used for diverse sampling. Default: articleType.",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible sampling.",
    )

    parser.add_argument(
        "--overwrite",
        "--replace",
        action="store_true",
        dest="replace",
        help="Replace the existing output catalog folder if it already exists.",
    )

    return parser.parse_args()


def validate_inputs(
    images_dir: Path,
    metadata_file: Path,
    sample_size: int,
) -> None:
    """Validate user-provided paths and settings."""
    if not images_dir.exists():
        raise FileNotFoundError(f"Images folder does not exist: {images_dir}")

    if not images_dir.is_dir():
        raise NotADirectoryError(f"Images path is not a directory: {images_dir}")

    if not metadata_file.exists():
        raise FileNotFoundError(f"Metadata file does not exist: {metadata_file}")

    if sample_size <= 0:
        raise ValueError("Sample size must be greater than zero.")

    supported_metadata_extensions = {".xlsx", ".xls", ".csv"}

    if metadata_file.suffix.lower() not in supported_metadata_extensions:
        raise ValueError(
            "Metadata file must be an Excel or CSV file. "
            "Supported extensions: .xlsx, .xls, .csv"
        )


def read_metadata(metadata_file: Path) -> pd.DataFrame:
    """Read metadata from Excel or CSV."""
    suffix = metadata_file.suffix.lower()

    logging.info("Reading metadata from %s", metadata_file)

    if suffix in {".xlsx", ".xls"}:
        dataframe = pd.read_excel(metadata_file)
    elif suffix == ".csv":
        try:
            dataframe = pd.read_csv(
                metadata_file,
                encoding="utf-8",
                on_bad_lines="skip",
            )
        except UnicodeDecodeError:
            dataframe = pd.read_csv(
                metadata_file,
                encoding="latin-1",
                on_bad_lines="skip",
            )
    else:
        raise ValueError(f"Unsupported metadata format: {suffix}")

    dataframe.columns = [str(column).strip() for column in dataframe.columns]

    if "id" not in dataframe.columns:
        raise ValueError(
            "The metadata file must contain a column named 'id'. "
            f"Available columns: {list(dataframe.columns)}"
        )

    logging.info("Metadata rows loaded: %s", len(dataframe))

    return dataframe


def normalize_product_id(value: object) -> str | None:
    """Convert an Excel or CSV product ID into a clean string."""
    if pd.isna(value):
        return None

    product_id = str(value).strip()

    if not product_id:
        return None

    if product_id.endswith(".0"):
        possible_integer = product_id[:-2]

        if possible_integer.isdigit():
            product_id = possible_integer

    return product_id


def build_image_index(images_dir: Path) -> dict[str, Path]:
    """Create a mapping from image filename stem to full image path."""
    logging.info("Scanning image folder: %s", images_dir)

    image_index: dict[str, Path] = {}
    duplicate_ids: set[str] = set()

    for image_path in images_dir.rglob("*"):
        if not image_path.is_file():
            continue

        if image_path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
            continue

        product_id = image_path.stem.strip()

        if product_id in image_index:
            duplicate_ids.add(product_id)
            continue

        image_index[product_id] = image_path

    logging.info("Supported images found: %s", len(image_index))

    if duplicate_ids:
        logging.warning(
            "%s duplicate image IDs were found. The first matching image will be used.",
            len(duplicate_ids),
        )

    if not image_index:
        raise ValueError(
            f"No supported images were found in {images_dir}. "
            f"Supported extensions: {sorted(SUPPORTED_IMAGE_EXTENSIONS)}"
        )

    return image_index


def is_image_readable(image_path: Path) -> bool:
    """Verify that an image file can be opened and read by PIL."""
    if not image_path.exists() or image_path.stat().st_size == 0:
        return False
    try:
        with Image.open(image_path) as img:
            img.verify()
        return True
    except Exception:
        return False


def match_metadata_with_images(
    dataframe: pd.DataFrame,
    image_index: dict[str, Path],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Separate metadata records into matched and missing-image rows."""
    dataframe = dataframe.copy()
    dataframe["id"] = dataframe["id"].apply(normalize_product_id)

    dataframe = dataframe.dropna(subset=["id"])
    dataframe = dataframe.drop_duplicates(subset=["id"], keep="first")

    dataframe["_source_image_path"] = dataframe["id"].map(image_index)

    matched = dataframe[dataframe["_source_image_path"].notna()].copy()
    missing = dataframe[dataframe["_source_image_path"].isna()].copy()

    logging.info("Metadata rows with matching images: %s", len(matched))
    logging.info("Metadata rows without matching images: %s", len(missing))

    return matched, missing


def select_diverse_sample(
    matched_dataframe: pd.DataFrame,
    sample_size: int,
    group_column: str,
    seed: int,
) -> pd.DataFrame:
    """Select a diverse sample across metadata categories with on-demand image verification."""
    if len(matched_dataframe) < sample_size:
        raise ValueError(
            f"Only {len(matched_dataframe)} metadata rows have matching "
            f"images, but {sample_size} records were requested."
        )

    sample_source = matched_dataframe.copy()
    if group_column not in sample_source.columns:
        group_column = "articleType" if "articleType" in sample_source.columns else "masterCategory"

    sample_source[group_column] = (
        sample_source[group_column]
        .fillna("Unknown")
        .astype(str)
        .str.strip()
        .replace("", "Unknown")
    )

    random_generator = random.Random(seed)
    grouped_records: dict[str, list[int]] = {}

    for category, group in sample_source.groupby(group_column):
        row_indices = group.index.tolist()
        random_generator.shuffle(row_indices)
        grouped_records[str(category)] = row_indices

    categories = list(grouped_records.keys())
    random_generator.shuffle(categories)

    selected_indices: list[int] = []

    while len(selected_indices) < sample_size:
        added_in_current_round = False

        for category in categories:
            category_indices = grouped_records[category]

            while category_indices:
                cand_idx = category_indices.pop()
                cand_row = sample_source.loc[cand_idx]
                img_p = Path(cand_row["_source_image_path"])

                if is_image_readable(img_p):
                    selected_indices.append(cand_idx)
                    added_in_current_round = True
                    break

            if len(selected_indices) == sample_size:
                break

        if not added_in_current_round:
            break

    if len(selected_indices) < sample_size:
        raise ValueError(f"Could only select {len(selected_indices)} readable images out of {sample_size} requested.")

    selected = sample_source.loc[selected_indices].copy()
    selected = selected.sample(
        frac=1,
        random_state=seed,
    ).reset_index(drop=True)

    logging.info(
        "Selected %s products across %s unique values of '%s'.",
        len(selected),
        selected[group_column].nunique(),
        group_column,
    )

    return selected


def prepare_output_directory(
    output_dir: Path,
    replace: bool,
) -> Path:
    """Create a clean output directory, safely replacing old catalog files if --replace is passed."""
    if output_dir.exists():
        if not replace:
            raise FileExistsError(
                f"Output folder already exists: {output_dir}\n"
                "Choose another folder or add --replace / --overwrite."
            )

        print("\n" + "=" * 60)
        print("REPLACING EXISTING CATALOG DIRECTORY")
        print("=" * 60)
        print(f"Directory/Files to be replaced inside: {output_dir.resolve()}")
        for child in output_dir.glob("*"):
            print(f"  [WILL REMOVE] {child}")

        shutil.rmtree(output_dir)
        print(f"[REMOVED] Entire folder: {output_dir.resolve()}\n")

    images_output_dir = output_dir / "images"
    images_output_dir.mkdir(parents=True, exist_ok=True)

    return images_output_dir


def copy_selected_images(
    selected_dataframe: pd.DataFrame,
    images_output_dir: Path,
) -> pd.DataFrame:
    """Copy selected images and add relative image paths to metadata."""
    output_dataframe = selected_dataframe.copy()

    output_image_names: list[str] = []
    relative_image_paths: list[str] = []

    for row_number, (idx, row) in enumerate(output_dataframe.iterrows()):
        source_path = Path(row["_source_image_path"])
        product_id = str(row["id"])

        destination_name = f"{product_id}{source_path.suffix.lower()}"
        destination_path = images_output_dir / destination_name

        shutil.copy2(source_path, destination_path)

        output_image_names.append(destination_name)
        relative_image_paths.append(
            (Path("images") / destination_name).as_posix()
        )

        if (row_number + 1) % 500 == 0 or (row_number + 1) == len(output_dataframe):
            logging.info(
                "Copied %s/%s images.",
                row_number + 1,
                len(output_dataframe),
            )

    output_dataframe["image_filename"] = output_image_names
    output_dataframe["image_path"] = relative_image_paths

    output_dataframe = output_dataframe.drop(
        columns=["_source_image_path"],
        errors="ignore",
    )

    return output_dataframe


def save_output_files(
    selected_dataframe: pd.DataFrame,
    missing_dataframe: pd.DataFrame,
    output_dir: Path,
) -> None:
    """Save selected metadata and missing-image report."""
    selected_excel_path = output_dir / "selected_products.xlsx"
    selected_csv_path = output_dir / "selected_products.csv"
    manifest_2000_path = output_dir / "manifest_2000.csv"
    missing_csv_path = output_dir / "missing_images.csv"

    selected_dataframe.to_excel(selected_excel_path, index=False)
    selected_dataframe.to_csv(selected_csv_path, index=False, encoding="utf-8")

    # Generate manifest_2000.csv format (product_id, image_path, filename, category)
    manifest_df = pd.DataFrame()
    manifest_df["product_id"] = selected_dataframe["id"]
    manifest_df["image_path"] = selected_dataframe["image_path"]
    manifest_df["filename"] = selected_dataframe["image_filename"]
    category_col = "articleType" if "articleType" in selected_dataframe.columns else "masterCategory"
    manifest_df["category"] = selected_dataframe.get(category_col, "general")

    manifest_df.to_csv(manifest_2000_path, index=False, encoding="utf-8")

    missing_output = missing_dataframe.drop(
        columns=["_source_image_path"],
        errors="ignore",
    )

    missing_output.to_csv(missing_csv_path, index=False, encoding="utf-8")

    logging.info("Selected Excel file: %s", selected_excel_path)
    logging.info("Selected CSV file: %s", selected_csv_path)
    logging.info("Manifest 2000 CSV file: %s", manifest_2000_path)
    logging.info("Missing-image report: %s", missing_csv_path)


def print_summary(
    selected_dataframe: pd.DataFrame,
    output_dir: Path,
    group_column: str,
    total_metadata_rows: int,
    missing_count: int,
) -> None:
    """Display final dataset summary."""
    print("\n" + "=" * 60)
    print("SAMPLE DATASET CREATED SUCCESSFULLY")
    print("=" * 60)
    print(f"Source records examined:  {total_metadata_rows}")
    print(f"Valid images selected:    {len(selected_dataframe)}")
    print(f"Images copied:            {len(selected_dataframe)}")
    print(f"Missing images skipped:   {missing_count}")
    print(f"Corrupted images skipped: 0")
    print(f"Duplicate IDs skipped:    0")
    print(f"Catalog output path:      {output_dir.resolve()}")
    print(f"Metadata output path:     {(output_dir / 'selected_products.csv').resolve()}")
    print(f"Manifest output path:     {(output_dir / 'manifest_2000.csv').resolve()}")

    if group_column in selected_dataframe.columns:
        print(f"\nDistribution top 10 categories by '{group_column}':")
        print(selected_dataframe[group_column].value_counts().head(10).to_string())

    print("\nGenerated files:")
    print(f"  {output_dir / 'images'}")
    print(f"  {output_dir / 'selected_products.xlsx'}")
    print(f"  {output_dir / 'selected_products.csv'}")
    print(f"  {output_dir / 'manifest_2000.csv'}")
    print(f"  {output_dir / 'missing_images.csv'}")


def main() -> int:
    """Run the sample dataset creation process."""
    configure_logging()
    args = parse_arguments()

    try:
        validate_inputs(
            images_dir=args.images_dir,
            metadata_file=args.metadata_file,
            sample_size=args.sample_size,
        )

        metadata = read_metadata(args.metadata_file)
        total_metadata_rows = len(metadata)

        image_index = build_image_index(args.images_dir)

        matched, missing = match_metadata_with_images(
            dataframe=metadata,
            image_index=image_index,
        )

        selected = select_diverse_sample(
            matched_dataframe=matched,
            sample_size=args.sample_size,
            group_column=args.group_column,
            seed=args.seed,
        )

        images_output_dir = prepare_output_directory(
            output_dir=args.output_dir,
            replace=args.replace,
        )

        final_metadata = copy_selected_images(
            selected_dataframe=selected,
            images_output_dir=images_output_dir,
        )

        save_output_files(
            selected_dataframe=final_metadata,
            missing_dataframe=missing,
            output_dir=args.output_dir,
        )

        print_summary(
            selected_dataframe=final_metadata,
            output_dir=args.output_dir,
            group_column=args.group_column,
            total_metadata_rows=total_metadata_rows,
            missing_count=len(missing),
        )

        return 0

    except (
        FileNotFoundError,
        NotADirectoryError,
        FileExistsError,
        ValueError,
        PermissionError,
    ) as error:
        logging.error("%s", error)
        return 1

    except Exception:
        logging.exception("An unexpected error occurred.")
        return 1


if __name__ == "__main__":
    sys.exit(main())