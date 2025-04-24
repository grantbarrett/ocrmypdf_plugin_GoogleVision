# OCRmyPDF Google Vision Plugin

This repository contains a plugin for [OCRmyPDF](https://github.com/ocrmypdf/OCRmyPDF) that allows using the [Google Cloud Vision API](https://cloud.google.com/vision) as the OCR (Optical Character Recognition) engine instead of the default Tesseract engine.

**Status:** This plugin is functional but should be considered **experimental**. It relies on external components and specific configurations. Use at your own discretion.

**Origin:** This repository was originally forked from [kkrell2016/ocrmypdf_plugin_GoogleVision](https://github.com/kkrell2016/ocrmypdf_plugin_GoogleVision). Significant modifications have been made since the fork to adapt to newer OCRmyPDF plugin interfaces, improve coordinate handling, and add features like baseline/font-size hints. Changes made here are specific to this repository and are **not** merged back into the original `kkrell2016` repository.

**Based On:** This work also incorporates code adapted from [dinosauria123/gcv2hocr](https://github.com/dinosauria123/gcv2hocr) for converting Google Cloud Vision API output to the hOCR format needed by OCRmyPDF.

## Features

* Performs OCR using Google Cloud Vision API’s `DOCUMENT_TEXT_DETECTION`.
* Integrates with OCRmyPDF via its plugin system (`--plugin` argument).
* Generates searchable PDF text layers based on GCV results.
* Attempts to map Tesseract language codes (used by OCRmyPDF's `-l` flag) to Google Cloud Vision language hints.
* Includes baseline and font size hints in the generated hOCR to improve text placement.

## Limitations & Dependencies

* **Tesseract Still Required:** This plugin currently relies on a separate installation of the Tesseract OCR engine for auxiliary functions like page orientation detection and deskewing. OCRmyPDF must be able to find your Tesseract installation for these features to work correctly. If Tesseract is not found, orientation/deskew steps will be skipped, potentially leading to incorrect page rotation or skewed text layers.
* **hOCR Conversion Quality:** Uses the included `gcv2hocr2.py` script for conversion. The accuracy of the final text placement depends heavily on the quality of this conversion and how well OCRmyPDF's renderer interprets the generated hOCR (including bounding boxes, baselines, and font sizes). While functional, further refinements might be needed for complex layouts or unusual fonts. Text placement may not be perfect.
* **Cost:** Using the Google Cloud Vision API incurs costs based on usage, although Google Cloud offers a free tier which may cover limited use. Please review the [Vision API Pricing](https://cloud.google.com/vision/pricing) page.
* **Compatibility:** Developed and tested against OCRmyPDF v16.10.0. Compatibility with significantly older or newer versions is not guaranteed due to potential changes in OCRmyPDF's plugin API.

## Prerequisites

Before installing and using this plugin, ensure you have the following:

1.  **OCRmyPDF:** A working installation of OCRmyPDF (v16.10.0 or compatible recommended). If you don't have it, follow the [official OCRmyPDF installation guide](https://ocrmypdf.readthedocs.io/en/latest/installation.html).
2.  **Python:** Python 3.10 or newer (check with `python3 --version`).
3.  **Tesseract:** The Tesseract OCR engine must be installed and findable in your system’s PATH. This is required for orientation and deskew functions used by the plugin. See [OCRmyPDF Documentation - Installing Tesseract](https://ocrmypdf.readthedocs.io/en/latest/installation.html#installing-tesseract).
4.  **Google Cloud Account & Setup:**
    * A Google Cloud Platform (GCP) project. [How-to Guide: Creating and Managing Projects](https://cloud.google.com/resource-manager/docs/creating-managing-projects).
    * The **Cloud Vision API** must be enabled for your project. [How-to Guide: Enabling and Disabling APIs](https://cloud.google.com/apis/docs/getting-started#enabling_apis) (Search for "Cloud Vision API"). Direct link to enable: [Enable Vision API](https://console.cloud.google.com/flows/enableapi?apiid=vision.googleapis.com).
    * Billing must be enabled for your project. [How-to Guide: Modify a Project's Billing Settings](https://cloud.google.com/billing/docs/how-to/modify-project).

## Installation

1.  **Clone the Repository:** Open your terminal or command prompt and run:
    ```bash
    git clone [https://github.com/grantbarrett/ocrmypdf_plugin_GoogleVision.git](https://github.com/grantbarrett/ocrmypdf_plugin_GoogleVision.git)
    cd ocrmypdf_plugin_GoogleVision
    ```
2.  **Create & Activate Virtual Environment (Highly Recommended):** This isolates dependencies and avoids conflicts with system packages.
    ```bash
    # Navigate into the cloned directory first if you haven't already
    python3 -m venv venv
    source venv/bin/activate  # On macOS/Linux
    # Or: venv\Scripts\activate.bat  # On Windows CMD
    # Or: .\venv\Scripts\Activate.ps1 # On Windows PowerShell
    ```
    Your terminal prompt should now start with `(venv)`.
3.  **Install Dependencies:** Install the required Python libraries into your active virtual environment:
    ```bash
    pip install -U pip
    pip install ocrmypdf google-cloud-vision Pillow reportlab
    ```

## Authentication for Google Cloud Vision

The plugin needs credentials to access the Google Cloud Vision API. Choose **one** of the following methods:

**Method 1: Application Default Credentials (ADC) - Recommended**

This is generally the easiest and most secure method for local use and many deployment types.

1.  **Install Google Cloud CLI (`gcloud`):** If you haven't already, follow the official instructions: [Install the gcloud CLI](https://cloud.google.com/sdk/docs/install).
2.  **Log in and Set ADC:** Run this command in your terminal (make sure your virtual environment from Step 2 above is still active) and follow the browser prompts to authenticate with the Google account linked to your GCP project:
    ```bash
    gcloud auth application-default login
    ```
    The plugin (`gvision.py`) will automatically detect and use these credentials when you run `ocrmypdf`.

**Method 2: Service Account Key File**

Use this method if ADC is not suitable for your environment (e.g., some automated systems).

1.  **Create a Service Account Key:**
    * Go to the Google Cloud Console -> IAM & Admin -> Service Accounts.
    * Select your GCP project.
    * Choose an existing service account or create a new one.
    * Ensure the service account has the necessary permissions to use the Vision API (e.g., the predefined `Cloud Vision AI User` role). [How-to Guide: Granting Roles to Service Accounts](https://cloud.google.com/iam/docs/granting-roles-to-service-accounts).
    * Create a JSON key for the service account and download it to a secure location on your computer. [How-to Guide: Creating and managing service account keys](https://cloud.google.com/iam/docs/creating-managing-service-account-keys). **Treat this file like a password; do not commit it to your repository.**
2.  **Use the Key File:** When running `ocrmypdf`, use the `--gcv-keyfile` argument (added by this plugin) and provide the full path to your downloaded JSON key file.

## Usage

1.  Make sure your virtual environment (e.g., `venv`) is activated.
2.  Run `ocrmypdf` from your terminal.
3.  Use the `--plugin` argument, providing the full path to the `gvision.py` script within the cloned repository directory.
4.  Use the `-l LANG1[+LANG2...]` argument to specify the language(s) in the document using Tesseract's 3-letter codes (e.g., `eng`, `deu`, `ara`, `chi_sim`). Separate multiple languages with `+`. The plugin will attempt to map these to appropriate Google Vision language hints for the API call.
5.  **Recommended:** Use `--pdf-renderer hocr`. This explicitly tells OCRmyPDF to use its hOCR-specific rendering pipeline. This seems necessary for reliable text placement with the hOCR generated by this plugin, especially compared to the default `sandwich` renderer which might be chosen automatically for certain languages (like RTL).
6.  **Optional:** If using a service account key file (Method 2 for Authentication), add the `--gcv-keyfile /path/to/your/keyfile.json` argument.
7.  **Optional:** Use `--force-ocr` if your input PDF might already contain some text, to ensure OCR is performed anyway.

## **Example Command (using ADC):**
  
ocrmypdf \\  
  \--plugin /path/to/cloned/repo/gvision.py \\  
  \-l eng+fra \\  
  \--pdf-renderer hocr \\  
  my\_document.pdf \\  
  my\_document\_ocr.pdf \\  
  \--force-ocr

**Example** Command **(using Service Account Key):**

ocrmypdf \\  
  \--plugin /path/to/cloned/repo/gvision.py \\  
  \--gcv-keyfile /secure/path/to/my-gcp-key.json \\  
  \-l ara+eng \\  
  \--pdf-renderer hocr \\  
  arabic\_doc.pdf \\  
  arabic\_doc\_ocr.pdf \\  
  \--force-ocr

*(Remember to replace /path/to/cloned/repo/ and /secure/path/to/my-gcp-key.json with your actual paths)*

## **How it Works (Simplified)**

1. OCRmyPDF starts processing the input PDF.  
2. When it needs to perform OCR on a page image, it calls the GVisionOcrEngine provided by the gvision.py plugin (because you specified \--plugin).  
3. The plugin authenticates with Google Cloud (using ADC or the key file).  
4. It sends the page image to the Google Cloud Vision API (document\_text\_detection), including mapped language hints based on your \-l argument.  
5. It receives a detailed JSON response containing the recognized text and its coordinates (as pixel vertices).  
6. The plugin uses the included gcv2hocr2.py script to:  
   * Detect the image DPI using the Pillow library.  
   * Convert the GCV pixel coordinates to PDF points (1/72 inch) using the detected DPI.  
   * Transform Y-coordinates to a bottom-left origin system suitable for PDF/hOCR.  
   * Generate an hOCR file (HTML format) embedding the text and its position information (bounding boxes in points, calculated baseline hints, estimated font size hints).  
7. OCRmyPDF's rendering pipeline (specifically the hocr renderer, when selected via \--pdf-renderer hocr) reads this hOCR file.  
8. The renderer creates an invisible text layer in the output PDF, attempting to match the position and scale specified in the hOCR.  
9. Auxiliary steps like orientation detection and deskewing are delegated to the installed Tesseract engine.

## Troubleshooting

* **`google.auth.exceptions.DefaultCredentialsError`:** Your Application Default Credentials are not set up correctly or cannot be found.
    * Ensure you have run `gcloud auth application-default login` in the *same terminal session* where you are running `ocrmypdf` (and where your virtual environment is active).
    * Make sure you authenticated with the Google account linked to the correct GCP project (the one with Vision API enabled).
    * Alternatively, switch to using the `--gcv-keyfile` method.
* **`ValueError: GCV key file not found`:** The path provided to `--gcv-keyfile` is incorrect or the file is not readable. Double-check the path and file permissions.
* **Text Layer Missing in Output PDF:**
    * Verify the Google Cloud Vision API call succeeded. Check the console output for any errors reported by `gvision.py` or messages starting with `google.api_core.exceptions`.
    * Run with `--keep-temporary-files` and check the temporary directory. Inside the subdirectories for each page (e.g., `page_001`), ensure both an `.hocr` file (e.g., `ocr.hocr`) and a `.txt` file (e.g., `000001_ocr_tess.txt`) were created.
    * Open the `.hocr` file. Does it contain valid HTML with `ocr_page`, `ocr_line`, and `ocrx_word` elements? Does it include the recognized text?
    * Confirm you are using the `--pdf-renderer hocr` argument when running `ocrmypdf`. The `sandwich` renderer may not correctly process the hOCR from this plugin.
* **Text Misaligned / Incorrect Position:**
    * This is the most common known issue with the current version. The text layer exists, but highlighting it shows it doesn't precisely overlay the text in the image.
    * **Ensure `--pdf-renderer hocr` is used.**
    * The misalignment likely stems from inaccuracies in converting the precise geometry (bounding boxes, font size, baseline) from the GCV response into the hOCR format, and how OCRmyPDF's renderer interprets these hints. The calculations in `gcv2hocr2.py` are heuristics and may not perfectly match the original font metrics or layout.
    * Check the console output for any "invalid line box" warnings during the run - if these reappear, there might still be coordinate calculation issues in `gcv2hocr2.py`.
    * Further improvements would likely require more sophisticated analysis of the GCV response or adjustments to the hOCR generation in `gcv2hocr2.py`.
* **Tesseract Errors (Orientation/Deskew):**
    * Ensure Tesseract is installed correctly and its executable is in your system's PATH environment variable. OCRmyPDF (and this plugin) needs to be able to run the `tesseract` command.
    * The plugin logs errors if it cannot find or execute Tesseract for these steps. The main OCR process will still use Google Vision, but pages might not be correctly rotated or deskewed.
* **Plugin Not Found / Import Errors:**
    * Make sure your virtual environment is active when running `ocrmypdf`.
    * Ensure all dependencies (`ocrmypdf`, `google-cloud-vision`, `Pillow`, `reportlab`) were installed correctly within the active virtual environment (`pip list`).
    * Verify the path provided to `--plugin` points correctly to the `gvision.py` file.

