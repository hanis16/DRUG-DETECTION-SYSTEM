from PIL import Image
import pytesseract

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

img = Image.open("test_image.jpg")  # put an image in same folder
text = pytesseract.image_to_string(img)

print(text)
