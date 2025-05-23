import torch
import torch.nn as nn
from PIL import Image
import open_clip
from BioMedClip.constants import MODEL_NAMES, MODEL_WEIGHTS

class BiomedCLIPEncoder:
    def __init__(self, model_name=MODEL_NAMES['biomedclip'],
                weights_path=MODEL_WEIGHTS['biomedclip']):
        # Load the model and image transforms
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(model_name)

        # Load fine-tuned weights if provided
        if weights_path:
            self.model.load_state_dict(torch.load(weights_path, map_location=torch.device('cpu'), weights_only=True))

        # Set model to evaluation mode
        self.model.eval()

        # Get feature dimensions (should be 512 for BiomedCLIP)
        self.feature_dim = 512

    def encode_image(self, image_path):
        # Load and preprocess the image
        image = Image.open(image_path).convert("RGB")
        image_input = self.preprocess(image).unsqueeze(0)  

        # Move to the same device as the model
        device = next(self.model.parameters()).device
        image_input = image_input.to(device)

        # Get image features
        with torch.no_grad():
            image_features = self.model.encode_image(image_input)
            # Normalize features
            image_features = image_features / image_features.norm(dim=1, keepdim=True)

        return image_features