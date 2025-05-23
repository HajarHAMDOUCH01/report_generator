import torch
import torch.nn as nn
from transformers import BioGptForCausalLM, BioGptTokenizer
from ..BioMedClip import BiomedCLIPEncoder 
from ..Q_former.q_former import Qformer

class XrayReportGenerator(nn.Module):
    def __init__(self, biomedclip_model_name, biomedclip_weights_path, qformer_config):
        super().__init__()
        self.biomedclip_encoder = BiomedCLIPEncoder(
            model_name=biomedclip_model_name,
            weights_path=biomedclip_weights_path
        )

        assert qformer_config.encoder_width == self.biomedclip_encoder.feature_dim, \
            "Q-Former encoder_width must match BiomedCLIP feature_dim"

        self.qformer = Qformer(qformer_config)

        self.tokenizer = BioGptTokenizer.from_pretrained("microsoft/biogpt")
        self.biogpt_decoder = BioGptForCausalLM.from_pretrained("microsoft/biogpt")

        biogpt_hidden_size = self.biogpt_decoder.config.hidden_size

        if qformer_config.hidden_size != biogpt_hidden_size:
            self.qformer_output_to_biogpt_input_projection = nn.Linear(
                qformer_config.hidden_size, biogpt_hidden_size
            )
        else:
            self.qformer_output_to_biogpt_input_projection = None

        self.eos_token_id = self.tokenizer.eos_token_id

        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token_id = self.tokenizer.eos_token_id 
            import warnings
            warnings.warn("Tokenizer pad_token_id not set, using eos_token_id as pad_token_id.")


    def forward(self, image_path, prompt_text: Optional[str] = None, max_new_tokens=50, num_beams=1, do_sample=False, top_k=None, top_p=None):
        image_features = self.biomedclip_encoder.encode_image(image_path)
        image_features_expanded = image_features.unsqueeze(1) # (batch_size, 1, 512)

        query_embeddings = self.qformer(image_features_expanded)

        if self.qformer_output_to_biogpt_input_projection:
            query_embeddings = self.qformer_output_to_biogpt_input_projection(query_embeddings)

        input_embeddings_list = [query_embeddings]
        input_attention_mask_list = [torch.ones(query_embeddings.shape[0], query_embeddings.shape[1], dtype=torch.long, device=query_embeddings.device)]

        if prompt_text:
            prompt_token_ids = self.tokenizer(prompt_text, return_tensors="pt", add_special_tokens=False).input_ids
            prompt_token_ids = prompt_token_ids.to(query_embeddings.device)
            text_embeddings = self.biogpt_decoder.get_input_embeddings()(prompt_token_ids)
            
            input_embeddings_list.append(text_embeddings)
            input_attention_mask_list.append(torch.ones(text_embeddings.shape[0], text_embeddings.shape[1], dtype=torch.long, device=text_embeddings.device))
        
        input_embeddings = torch.cat(input_embeddings_list, dim=1)
        input_attention_mask = torch.cat(input_attention_mask_list, dim=1)


        generated_output = self.biogpt_decoder.generate(
            inputs_embeds=input_embeddings,
            attention_mask=input_attention_mask,
            max_new_tokens=max_new_tokens,
            num_beams=num_beams, 
            do_sample=do_sample, 
            top_k=top_k,
            top_p=top_p,
            eos_token_id=self.eos_token_id, 
            pad_token_id=self.tokenizer.pad_token_id, 
        )

        generated_report = self.tokenizer.decode(generated_output[0], skip_special_tokens=True)

        return generated_report