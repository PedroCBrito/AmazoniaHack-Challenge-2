# How-to guides

## Use Textract with `dev-ocr`

Set these values in `.env.local`:

```env
OCR_PROVIDER=textract
AWS_PROFILE=amazonia2026-textract
AWS_REGION=eu-central-1
```

Verify the profile:

```bash
aws sts get-caller-identity --profile amazonia2026-textract
```

Start only the adapter:

```bash
just dev-ocr
```

Send an image directly to Textract:

```bash
curl --fail-with-body --max-time 180 \
  -F image=@path/to/document.jpg \
  http://127.0.0.1:9000/ocr
```

## Use Textract with Docker

Set the provider and AWS profile in `.env.local`:

```env
OCR_PROVIDER=textract
AWS_PROFILE=amazonia2026-textract
AWS_REGION=eu-central-1
AWS_CONFIG_DIR=/absolute/path/to/your/.aws
OCR_CONTAINER_UID=0
OCR_CONTAINER_GID=0
```

`AWS_CONFIG_DIR` points to the host directory containing `config` and `credentials`. Compose mounts it read-only at `/tmp/aws`. With rootless Docker, container UID/GID `0` can read host AWS files with mode `600`.

Start the stack:

```bash
just start
```

## Switch back to Chandra

Set `OCR_PROVIDER=chandra`, then run `just start` or `just dev-ocr` again.

## Run locally with hot reload

Use two terminals:

```bash
just dev-ocr
just dev-api
```

Run the tests with:

```bash
just test
```

## Export the hackathon JSON

With the API and the selected OCR backend running:

```bash
python -m scripts.export_json documents/document.jpg --output-dir outputs
```

This creates `outputs/document.json` after validating the response. Supply
multiple image paths to process them sequentially. Use a new output directory
for each comparison run: the command never overwrites existing JSON files.
See [field mapping](field-mapping.md) for supported labels and review semantics.
