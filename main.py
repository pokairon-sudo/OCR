import cv2
import easyocr

# Load the image
image_path = './Captcha.jpg'  # Update this to your actual image path
image = cv2.imread(image_path)

# Check if the image was loaded successfully
if image is None:
    print("Error: Could not load image.")
    exit()

# Convert the image to grayscale
gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

# Apply thresholding (optional)
_, thresh_image = cv2.threshold(gray_image, 149, 255, cv2.THRESH_BINARY_INV)

# Initialize EasyOCR Reader
reader = easyocr.Reader(['en'])

# Perform OCR on the image
results = reader.readtext(thresh_image)

# Set confidence threshold
confidence_threshold = 0.5  # Adjust this value as needed

# Print results based on confidence threshold
for (bbox, text, prob) in results:
    if prob >= confidence_threshold:  # Check if confidence meets the threshold
        (top_left, top_right, bottom_right, bottom_left) = bbox
        top_left = tuple(map(int, top_left))
        bottom_right = tuple(map(int, bottom_right))
        
        # Draw rectangle around detected text
        cv2.rectangle(image, top_left, bottom_right, (0, 255, 0), 2)
        # Print detected number with probability
        print(f'Detected Number: {text} (Confidence: {prob:.2f})')

# Show the image with detected text
cv2.imshow('Detected Text', image)
cv2.waitKey(0)
cv2.destroyAllWindows()
