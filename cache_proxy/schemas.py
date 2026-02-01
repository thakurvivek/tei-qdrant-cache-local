from pydantic import BaseModel, Field
from typing import List, Union, Optional

class EmbedRequest(BaseModel):
    # Accept both 'input' (singular, used by OpenAI/sglang) and 'inputs' (plural, used by TEI)
    input: Union[str, List[str]] = None
    inputs: Union[str, List[str]] = None
    # Add other potential TEI parameters if needed, e.g., truncate: bool = False
    normalize: Optional[bool] = None # Pass through common params
    prompt_name: Optional[str] = None
    prompt: Optional[str] = None
    model: Optional[str] = None  # Add model parameter support
    encoding_format: Optional[str] = None  # Add encoding_format parameter support
    
    def get_inputs(self) -> Union[str, List[str]]:
        """Return the actual inputs from either 'input' or 'inputs' field"""
        if self.input is not None:
            return self.input
        if self.inputs is not None:
            return self.inputs
        raise ValueError("Either 'input' or 'inputs' must be provided")

# We expect TEI to return a list of lists (embeddings)
class TEIEmbedResponse(BaseModel):
    data: List[List[float]]
    # Include other fields if TEI adds them, like usage stats
    usage: Optional[dict] = None  # Add usage stats support

# Response model for cache proxy - wraps embeddings in data field
class CacheProxyResponse(BaseModel):
    data: List[List[float]]
    usage: Optional[dict] = None
    usage: Optional[dict] = None  # Add usage stats support

# Using Any to simplify, TEI might return List[List[float]] or Dict with embeddings
class GenericTEIResponse(BaseModel):
     embeddings: List[List[float]] = Field(alias="result") # Adapt based on actual TEI response structure if needed