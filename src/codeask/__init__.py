"""CodeAsk: private-deployment R&D Q&A system."""

import os

# LiteLLM otherwise tries to fetch its model cost map from GitHub at import
# time. CodeAsk should stay offline by default for private deployments.
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"

__version__ = "0.1.0"
