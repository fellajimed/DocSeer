import torch


def get_device(device: str | None = None) -> torch.device:
    if device is not None:
        return torch.device(device)
    elif torch.backends.mps.is_available():
        return torch.device('mps')
    elif torch.cuda.is_available():
        return torch.device('cuda')
    else:
        return torch.device('cpu')
