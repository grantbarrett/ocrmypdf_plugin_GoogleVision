# Refined Google Vision OCR Engine Plugin for OCRmyPDF
# Based on grantbarrett/ocrmypdf_plugin_GoogleVision
# Addresses issues with modern OCRmyPDF plugin interface, authentication,
# language handling, and text extraction.
# Added DPI detection and passing to hOCR generator.

import logging
import pathlib
import io
import os
import sys
import json
from argparse import ArgumentParser, Namespace
from typing import List, Tuple, Optional, Set # Added Set for languages return type

# --- OCRmyPDF Imports ---
try:
    from ocrmypdf import hookimpl
    import ocrmypdf.exceptions # Import the whole module
    from ocrmypdf.pluginspec import OcrEngine
    from ocrmypdf._exec import tesseract # Still needed for orientation/deskew AND languages
except ImportError as e:
    print(f"Fatal Error importing core ocrmypdf components: {e}. "
          "Please ensure ocrmypdf v16.10.0 (or compatible) is installed correctly in the active environment.")
    sys.exit(1)


# --- Google Cloud Vision Imports ---
try:
    from google.cloud import vision
    from google.cloud.vision_v1 import AnnotateImageResponse
    import google.api_core.exceptions
    import importlib.metadata
except ImportError:
    print("Error: google-cloud-vision library not found. pip install google-cloud-vision")
    sys.exit(1)

# --- Image Library Import ---
try:
    from PIL import Image, UnidentifiedImageError
except ImportError:
    print("Error: Pillow library not found. pip install Pillow")
    sys.exit(1)


# --- Local hOCR Conversion Module ---
# Ensure gcv2hocr2.py is in the same directory or Python path
try:
    _plugin_dir = os.path.dirname(os.path.abspath(__file__))
    if _plugin_dir not in sys.path:
        sys.path.insert(0, _plugin_dir)
    import gcv2hocr2
    if _plugin_dir == sys.path[0]:
        sys.path.pop(0)
except ImportError:
    print(f"Error: Could not import gcv2hocr2.py. Make sure it's in the same directory as gvision.py ({_plugin_dir}).")
    sys.exit(1)
except NameError:
     print("Error determining plugin directory. Cannot reliably import gcv2hocr2.py.")
     sys.exit(1)


# --- Setup ---
log = logging.getLogger(__name__)

# --- Plugin Hooks ---

@hookimpl
def add_options(parser: ArgumentParser):
    """Adds command-line options specific to this plugin."""
    gcv_group = parser.add_argument_group(
        "Google Vision Plugin Options",
        "Options for the OCRmyPDF Google Cloud Vision OCR Engine plugin"
    )
    gcv_group.add_argument(
        '--gcv-keyfile',
        help="Path to Google Cloud service account JSON key file. "
             "If not set, Application Default Credentials (ADC) are used."
    )

@hookimpl
def check_options(options: Namespace):
    """Validates plugin-specific options."""
    if not hasattr(options, 'gcv_keyfile'):
        options.gcv_keyfile = None
    if options.gcv_keyfile and not pathlib.Path(options.gcv_keyfile).is_file():
        log.error(f"Google Cloud Vision key file not found: {options.gcv_keyfile}")
        raise ValueError(f"GCV key file not found: {options.gcv_keyfile}")
    log.info("Google Vision plugin options checked.")


# --- OCR Engine Implementation ---

class GVisionOcrEngine(OcrEngine):
    """
    OCRmyPDF Engine implementation using Google Cloud Vision API.
    """

    def __init__(self, options: Optional[Namespace] = None):
        """Initialize the engine, potentially using options."""
        self.options = options if options else Namespace()
        if not hasattr(self.options, 'gcv_keyfile'):
            self.options.gcv_keyfile = None
        self.gcv_client = None
        log.info("GVisionOcrEngine initialized")

    def __str__(self):
        """Return a string representation of the engine."""
        return f"Google Vision OCR Engine (google-cloud-vision v{self.version()})"


    def _initialize_client(self):
        """Initializes the GCV client based on options."""
        if self.gcv_client is None:
            keyfile = getattr(self.options, 'gcv_keyfile', None)
            try:
                if keyfile:
                    log.info(f"Using GCV key file: {keyfile}")
                    self.gcv_client = vision.ImageAnnotatorClient.from_service_account_json(keyfile)
                else:
                    log.info("Using Application Default Credentials (ADC) for GCV.")
                    self.gcv_client = vision.ImageAnnotatorClient()
            except Exception as e:
                log.exception(f"Failed to initialize Google Cloud Vision client: {e}")
                raise EnvironmentError("Could not initialize GCV client. Check credentials/keyfile.") from e

    @staticmethod
    def get_name():
        """Return the unique name of this engine."""
        return "google_vision"

    @staticmethod
    def check_availability(options: Optional[Namespace] = None) -> bool:
        """Check if the engine and its dependencies are available."""
        log.info("Google Cloud Vision library is available.")
        if not tesseract.check_available():
             log.error("Tesseract executable not found, which is required by the GCV plugin for auxiliary functions.")
             return False
        log.info("Tesseract executable found for auxiliary functions.")
        return True

    @staticmethod
    def version() -> str:
        """Return the version of the underlying library."""
        try:
            return importlib.metadata.version('google-cloud-vision')
        except importlib.metadata.PackageNotFoundError:
            return "google-cloud-vision (unknown version)"

    @staticmethod
    def creator_tag(options: Optional[Namespace] = None) -> str:
        """Return the PDF producer string for this engine."""
        current_options = options if options else Namespace()
        return f"OCRmyPDF-Plugin-GoogleVision {GVisionOcrEngine.version()}"

    @staticmethod
    def languages(options: Namespace) -> Set[str]:
        """
        Return the set of *all* languages supported by the installed Tesseract.
        """
        try:
            tess_langs = tesseract.get_languages()
            log.debug(f"Reporting all available Tesseract languages to OCRmyPDF core: {tess_langs}")
            return tess_langs
        except Exception as e:
            log.exception("Failed to get languages from Tesseract. Reporting minimal set {'eng'}.")
            return {'eng'}


    @staticmethod
    def _map_languages_for_gcv(options: Namespace) -> List[str]:
        """
        Internal helper to map Tesseract language codes to GCV BCP-47 codes
        for the actual API call.
        """
        current_options = options if options else Namespace()
        tesseract_langs_str = getattr(current_options, 'language', 'eng')
        tesseract_langs = tesseract_langs_str.split('+')

        lang_map = {
            'afr': 'af', 'amh': 'am', 'ara': 'ar', 'asm': 'as', 'aze': 'az',
            'aze_cyrl': 'az-Cyrl', 'bel': 'be', 'ben': 'bn', 'bod': 'bo',
            'bos': 'bs', 'bre': 'br', 'bul': 'bg', 'cat': 'ca', 'ceb': 'ceb',
            'ces': 'cs', 'chi_sim': 'zh-Hans', 'chi_tra': 'zh-Hant', 'chr': 'chr',
            'cos': 'co', 'cym': 'cy', 'dan': 'da', 'dan_frak': 'da', 'deu': 'de',
            'deu_frak': 'de', 'deu_latf': 'de', 'dzo': 'dz', 'ell': 'el',
            'eng': 'en', 'enm': 'en', 'epo': 'eo', 'est': 'et', 'eus': 'eu',
            'fao': 'fo', 'fas': 'fa', 'fil': 'fil', 'fin': 'fi', 'fra': 'fr',
            'frk': 'de', 'frm': 'fr', 'fry': 'fy', 'gla': 'gd', 'gle': 'ga',
            'glg': 'gl', 'grc': 'el', 'guj': 'gu', 'hat': 'ht', 'heb': 'he',
            'hin': 'hi', 'hrv': 'hr', 'hun': 'hu', 'hye': 'hy', 'iku': 'iu',
            'ind': 'id', 'isl': 'is', 'ita': 'it', 'ita_old': 'it', 'jav': 'jv',
            'jpn': 'ja', 'kan': 'kn', 'kat': 'ka', 'kat_old': 'ka', 'kaz': 'kk',
            'khm': 'km', 'kir': 'ky', 'kmr': 'ku', 'kor': 'ko', 'kor_vert': 'ko',
            'kur': 'ku', 'lao': 'lo', 'lat': 'la', 'lav': 'lv', 'lit': 'lt',
            'ltz': 'lb', 'mal': 'ml', 'mar': 'mr', 'mkd': 'mk', 'mlt': 'mt',
            'mon': 'mn', 'mri': 'mi', 'msa': 'ms', 'mya': 'my', 'nep': 'ne',
            'nld': 'nl', 'nor': 'no', 'oci': 'oc', 'ori': 'or', 'pan': 'pa',
            'pol': 'pl', 'por': 'pt', 'pus': 'ps', 'que': 'qu', 'ron': 'ro',
            'rus': 'ru', 'san': 'sa', 'sin': 'si', 'slk': 'sk', 'slk_frak': 'sk',
            'slv': 'sl', 'snd': 'sd', 'spa': 'es', 'spa_old': 'es', 'sqi': 'sq',
            'srp': 'sr-Cyrl', 'srp_latn': 'sr-Latn', 'sun': 'su', 'swa': 'sw',
            'swe': 'sv', 'syr': 'syr', 'tam': 'ta', 'tat': 'tt', 'tel': 'te',
            'tgk': 'tg', 'tgl': 'tl', 'tha': 'th', 'tir': 'ti', 'ton': 'to',
            'tur': 'tr', 'uig': 'ug', 'ukr': 'uk', 'urd': 'ur', 'uzb': 'uz',
            'uzb_cyrl': 'uz-Cyrl', 'vie': 'vi', 'yid': 'yi', 'yor': 'yo',
        }
        gcv_langs = []
        unmapped = []
        for lang in tesseract_langs:
            mapped_lang = lang_map.get(lang)
            if mapped_lang:
                gcv_langs.append(mapped_lang)
            else:
                gcv_langs.append(lang)
                unmapped.append(lang)
        if unmapped:
            log.warning(f"Language codes {unmapped} have no direct GCV mapping in plugin, using original codes as hints.")

        log.info(f"Mapping Tesseract languages '{tesseract_langs_str}' to GCV hints for API call: {gcv_langs}")
        return gcv_langs

    def _get_image_dpi(self, image_path: pathlib.Path) -> Tuple[Optional[float], Optional[float]]:
        """Helper function to get DPI from an image file using Pillow."""
        try:
            with Image.open(image_path) as img:
                dpi = img.info.get('dpi')
                if dpi and isinstance(dpi, (tuple, list)) and len(dpi) == 2:
                    log.debug(f"Detected DPI for {image_path.name}: {dpi}")
                    return float(dpi[0]), float(dpi[1])
                else:
                    log.warning(f"Could not reliably determine DPI for {image_path.name}. DPI info: {dpi}")
                    return None, None
        except UnidentifiedImageError:
            log.error(f"Pillow could not identify image file: {image_path}")
            return None, None
        except Exception as e:
            log.exception(f"Error reading DPI from {image_path.name}: {e}")
            return None, None


    def generate_hocr(self, input_file: pathlib.Path, output_hocr: pathlib.Path, output_text: pathlib.Path, options: Namespace):
        """
        Perform OCR using GCV and produce hOCR and plain text files.
        """
        self.options = options if options else Namespace()
        if not hasattr(self.options, 'gcv_keyfile'):
             self.options.gcv_keyfile = None

        self._initialize_client()

        log.info(f"[{self.get_name()}] Performing OCR on {input_file.name}")

        # --- Get image DPI ---
        image_dpi_x, image_dpi_y = self._get_image_dpi(input_file)
        if image_dpi_x is None or image_dpi_y is None:
             log.warning(f"Using default DPI of 72 for {input_file.name} due to detection issues. Text placement may be inaccurate.")
             # Use a default DPI if detection fails, common default is 72 but 300 might be better for scans
             image_dpi_x = image_dpi_y = getattr(options, 'image_dpi', 300.0) # Allow override or default to 300

        try:
            # Read image content
            with io.open(input_file, 'rb') as image_file:
                content = image_file.read()
            image = vision.Image(content=content)

            # Prepare GCV request
            features = [vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)]
            language_hints = self._map_languages_for_gcv(options)
            image_context = vision.ImageContext(language_hints=language_hints)
            request = vision.AnnotateImageRequest(image=image, features=features, image_context=image_context)

            # Make the API call
            log.debug(f"[{self.get_name()}] Sending request to GCV API...")
            response = self.gcv_client.annotate_image(request=request)
            log.debug(f"[{self.get_name()}] Received response from GCV API.")

            if response.error.message:
                log.error(f"GCV API Error for {input_file.name}: {response.error.message}")
                raise ocrmypdf.exceptions.ExecError(f"GCV API Error: {response.error.message}")

            if not response.full_text_annotation:
                 log.warning(f"[{self.get_name()}] GCV returned no text annotation for {input_file.name}. Generating empty output.")
                 output_hocr.touch()
                 output_text.touch()
                 return

            # Convert GCV JSON response to hOCR using gcv2hocr2 module
            json_response_str = AnnotateImageResponse.to_json(response)
            gcv_dict = json.loads(json_response_str)
            resp_for_gcv = {"responses": [gcv_dict]}

            log.debug(f"[{self.get_name()}] Converting GCV response to hOCR using gcv2hocr2...")
            # --- Pass DPI to the converter ---
            hocr_page_obj = gcv2hocr2.fromResponse(
                resp_for_gcv,
                input_file.stem,
                image_dpi_x=image_dpi_x, # Pass detected DPI X
                image_dpi_y=image_dpi_y  # Pass detected DPI Y
            )
            hocr_content = hocr_page_obj.render()

            if hocr_content:
                log.debug(f"[{self.get_name()}] Generated hOCR content (first 500 chars): {hocr_content[:500]}")
            else:
                log.warning(f"[{self.get_name()}] Generated hOCR content is EMPTY for {input_file.name}")
            log.debug(f"[{self.get_name()}] Attempting to write hOCR to: {output_hocr}")
            log.debug(f"[{self.get_name()}] hOCR conversion complete.")

            plain_text_content = response.full_text_annotation.text

            # Write the output files
            try:
                log.debug(f"[{self.get_name()}] Writing hOCR file...")
                with open(output_hocr, "w", encoding="utf-8") as f_hocr:
                    f_hocr.write(hocr_content)
                log.debug(f"[{self.get_name()}] Finished writing hOCR file.")

                log.debug(f"[{self.get_name()}] Writing plain text file to: {output_text}")
                with open(output_text, "w", encoding="utf-8") as f_text:
                    f_text.write(plain_text_content if plain_text_content else "")
                log.debug(f"[{self.get_name()}] Finished writing plain text file.")

                log.info(f"[{self.get_name()}] Successfully generated and wrote hOCR and text for {input_file.name}")
            except IOError as e:
                 log.error(f"Failed to write output files for {input_file.name}: {e}")
                 raise ocrmypdf.exceptions.ExecError(f"IOError writing output: {e}") from e

        except google.api_core.exceptions.GoogleAPICallError as e:
            log.exception(f"Google API Call Error during GCV OCR for {input_file.name}: {e}")
            raise ocrmypdf.exceptions.ExecError(f"GCV API Call Error: {e}") from e
        except ocrmypdf.exceptions.ExecError:
             raise
        except Exception as e:
            log.exception(f"Unexpected error during GCV OCR for {input_file.name}: {e}")
            raise RuntimeError(f"Plugin error during GCV OCR: {e}") from e

    def generate_text_only_pdf(self, input_file: pathlib.Path, output_pdf: pathlib.Path, output_text: pathlib.Path, options: Namespace):
        """
        Perform OCR and produce a text-only PDF.
        """
        self.options = options if options else Namespace()
        if not hasattr(self.options, 'gcv_keyfile'):
             self.options.gcv_keyfile = None

        log.warning(
            f"[{self.get_name()}] generate_text_only_pdf is not fully implemented. "
            f"Generating hOCR+text and an empty PDF for {input_file.name}."
        )
        hocr_temp = output_pdf.parent / f"{output_pdf.stem}.hocr"
        log.debug(f"[{self.get_name()}] Temp hOCR path for text_only_pdf: {hocr_temp}")

        try:
            # generate_hocr needs to be called to get text output
            self.generate_hocr(input_file, hocr_temp, output_text, options)

            try:
                from reportlab.pdfgen import canvas
                c = canvas.Canvas(str(output_pdf))
                c.setTitle(f"Text Layer for {input_file.name}")
                c.setAuthor(self.creator_tag(options))
                c.save()
                log.info(f"[{self.get_name()}] Created empty placeholder PDF: {output_pdf.name}")
            except ImportError:
                log.error("reportlab not found, cannot create empty PDF for text-only output.")
                output_pdf.touch()
            except Exception as e:
                 log.error(f"Failed to create empty PDF: {e}")
                 output_pdf.touch()

        finally:
            if hocr_temp.exists():
                try:
                    log.debug(f"[{self.get_name()}] Keeping temporary hOCR file for inspection: {hocr_temp}")
                    pass # Keep hocr file for inspection
                except OSError as e:
                    log.warning(f"Could not remove temporary hOCR file {hocr_temp}: {e}")
            else:
                 log.warning(f"[{self.get_name()}] Temporary hOCR file not found at expected path: {hocr_temp}")


    def generate_pdf(self, input_file: pathlib.Path, output_pdf: pathlib.Path, output_text: pathlib.Path, options: Namespace):
        """
        Delegate to generate_text_only_pdf to satisfy the interface call.
        """
        log.warning(f"[{self.get_name()}] generate_pdf called unexpectedly; delegating to generate_text_only_pdf.")
        self.generate_text_only_pdf(input_file, output_pdf, output_text, options)


    # --- Delegate Orientation/Deskew to Tesseract ---
    @staticmethod
    def get_orientation(input_file: pathlib.Path, options: Namespace) -> Tuple[int, float]:
        """Delegate orientation check to Tesseract."""
        current_options = options if options else Namespace()
        if not hasattr(current_options, 'tesseract_oem'): current_options.tesseract_oem = None
        if not hasattr(current_options, 'tesseract_timeout'): current_options.tesseract_timeout = 180.0

        log.debug(f"[{GVisionOcrEngine.get_name()}] Delegating orientation check to Tesseract for {input_file.name}")
        try:
            return tesseract.get_orientation(
                input_file,
                engine_mode=current_options.tesseract_oem,
                timeout=current_options.tesseract_timeout,
            )
        except FileNotFoundError:
            log.error("Tesseract not found. Orientation check requires Tesseract.")
            return (0, 0.0)
        except Exception as e:
            log.exception(f"Error during Tesseract orientation check: {e}")
            return (0, 0.0)

    @staticmethod
    def get_deskew(input_file: pathlib.Path, options: Namespace) -> float:
        """Delegate deskew check to Tesseract."""
        current_options = options if options else Namespace()
        if not hasattr(current_options, 'language'): current_options.language = 'eng'
        if not hasattr(current_options, 'tesseract_oem'): current_options.tesseract_oem = None
        if not hasattr(current_options, 'tesseract_timeout'): current_options.tesseract_timeout = 180.0

        log.debug(f"[{GVisionOcrEngine.get_name()}] Delegating deskew check to Tesseract for {input_file.name}")
        try:
             tess_langs_list = list(getattr(current_options, 'language', 'eng').split('+'))
             return tesseract.get_deskew(
                 input_file,
                 languages=tess_langs_list,
                 engine_mode=current_options.tesseract_oem,
                 timeout=current_options.tesseract_timeout,
             )
        except FileNotFoundError:
            log.error("Tesseract not found. Deskew check requires Tesseract.")
            return 0.0
        except Exception as e:
            log.exception(f"Error during Tesseract deskew check: {e}")
            return 0.0

# --- OCRmyPDF Engine Registration ---

@hookimpl
def get_ocr_engine() -> OcrEngine:
    """Registers the GVisionOcrEngine with OCRmyPDF."""
    return GVisionOcrEngine()
