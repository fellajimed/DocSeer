import torch
import requests
import xml.etree.ElementTree as ET


def get_device(device: str | None = None) -> torch.device:
    if device is not None:
        return torch.device(device)
    elif torch.backends.mps.is_available():
        return torch.device('mps')
    elif torch.cuda.is_available():
        return torch.device('cuda')
    else:
        return torch.device('cpu')


def get_sitemap_urls(sitemap_url: str) -> list[str]:
    """Fetches and parses a sitemap XML file to extract URLs.

    Args:
        sitemap_url: The sitemap.xml URL of the website

    Returns:
        List of URLs found in the sitemap. If sitemap is not found,
        returns a list containing only the base URL.

    Raises:
        ValueError: If there's an error fetching or parsing the sitemap
    """
    try:
        assert sitemap_url.endswith('sitemap.xml')

        # Fetch sitemap URL
        response = requests.get(sitemap_url, timeout=10)
        response.raise_for_status()

        # Parse XML content
        root = ET.fromstring(response.content)

        # Handle different XML namespaces that sitemaps might use
        namespaces = (
            {"ns": root.tag.split("}")[0].strip("{")}
            if "}" in root.tag else ""
        )

        # Extract URLs using namespace if present
        it = (root.findall(".//ns:loc", namespaces)
              if namespaces else root.findall(".//loc"))

        return [elem.text for elem in it]

    except requests.RequestException as e:
        raise ValueError(f"Failed to fetch sitemap: {str(e)}")
    except ET.ParseError as e:
        raise ValueError(f"Failed to parse sitemap XML: {str(e)}")
    except Exception as e:
        raise ValueError(f"Unexpected error processing sitemap: {str(e)}")
