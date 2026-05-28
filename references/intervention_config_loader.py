"""
Configuration Loader for Intervention Assessment

This module loads configuration from intervention_config.json and applies it
to the intervention_assessment module. This allows clinical teams to update
ICD mappings, specialty scores, and thresholds without touching code.

Usage:
    from intervention_config_loader import load_and_apply_config
    
    # Load config and update the assessment module
    load_and_apply_config("intervention_config.json")
    
    # Now use intervention_assessment as normal
    from intervention_assessment import assess_intervention, ClinicalInput, AdherenceInput
    ...
"""

import json
from pathlib import Path
from typing import Optional
import intervention_assessment as ia


def load_config(config_path: str = "intervention_config.json") -> dict:
    """
    Load configuration from JSON file.
    
    Args:
        config_path: Path to the configuration JSON file
        
    Returns:
        Configuration dictionary
        
    Raises:
        FileNotFoundError: If config file doesn't exist
        json.JSONDecodeError: If config file is invalid JSON
    """
    config_file = Path(config_path)
    
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with open(config_file, "r", encoding="utf-8") as f:
        return json.load(f)


def apply_config(config: dict) -> dict:
    """
    Apply configuration to the intervention_assessment module.
    
    Args:
        config: Configuration dictionary loaded from JSON
        
    Returns:
        Dictionary with applied changes summary
    """
    changes = {
        "critical_codes": False,
        "chapter_scores": False,
        "specialty_scores": False,
        "keywords": False
    }
    
    # Apply critical ICD codes
    if "critical_codes" in config and "codes" in config["critical_codes"]:
        codes = {item["code"] for item in config["critical_codes"]["codes"]}
        ia.update_icd_critical_codes(codes)
        changes["critical_codes"] = True
    
    # Apply chapter scores
    if "chapter_scores" in config and "mappings" in config["chapter_scores"]:
        scores = {
            item["prefix"]: item["score"] 
            for item in config["chapter_scores"]["mappings"]
        }
        ia.update_icd_chapter_scores(scores)
        changes["chapter_scores"] = True
    
    # Apply specialty scores
    if "specialty_scores" in config and "mappings" in config["specialty_scores"]:
        scores = {
            item["specialty"]: item["score"]
            for item in config["specialty_scores"]["mappings"]
        }
        ia.update_specialty_scores(scores)
        changes["specialty_scores"] = True
    
    # Apply keywords (requires updating module globals directly)
    if "keywords" in config:
        keywords = config["keywords"]
        if "critical" in keywords:
            ia.CRITICAL_KEYWORDS = keywords["critical"]
            changes["keywords"] = True
        if "surgical" in keywords:
            ia.SURGICAL_KEYWORDS = keywords["surgical"]
        if "chronic" in keywords:
            ia.CHRONIC_KEYWORDS = keywords["chronic"]
    
    return changes


def load_and_apply_config(config_path: str = "intervention_config.json") -> dict:
    """
    Load configuration from file and apply to intervention_assessment module.
    
    This is the main function to use. Call this once at application startup
    before using any intervention_assessment functions.
    
    Args:
        config_path: Path to the configuration JSON file
        
    Returns:
        Dictionary with config version and applied changes
        
    Example:
        >>> from intervention_config_loader import load_and_apply_config
        >>> result = load_and_apply_config("intervention_config.json")
        >>> print(result)
        {'version': '1.0.0', 'changes': {'critical_codes': True, ...}}
    """
    config = load_config(config_path)
    changes = apply_config(config)
    
    return {
        "version": config.get("version", "unknown"),
        "last_updated": config.get("last_updated", "unknown"),
        "changes": changes
    }


def get_config_summary(config_path: str = "intervention_config.json") -> dict:
    """
    Get a summary of the configuration without applying it.
    
    Useful for displaying current configuration to users.
    
    Args:
        config_path: Path to the configuration JSON file
        
    Returns:
        Summary dictionary with counts and key settings
    """
    config = load_config(config_path)
    
    summary = {
        "version": config.get("version", "unknown"),
        "last_updated": config.get("last_updated", "unknown"),
        "updated_by": config.get("updated_by", "unknown"),
        "counts": {}
    }
    
    if "critical_codes" in config and "codes" in config["critical_codes"]:
        summary["counts"]["critical_codes"] = len(config["critical_codes"]["codes"])
    
    if "chapter_scores" in config and "mappings" in config["chapter_scores"]:
        summary["counts"]["icd_mappings"] = len(config["chapter_scores"]["mappings"])
    
    if "specialty_scores" in config and "mappings" in config["specialty_scores"]:
        summary["counts"]["specialty_mappings"] = len(config["specialty_scores"]["mappings"])
    
    if "thresholds" in config:
        summary["thresholds"] = config["thresholds"]
    
    if "adherence_weights" in config:
        summary["adherence_weights"] = config["adherence_weights"]
    
    return summary


def validate_config(config_path: str = "intervention_config.json") -> dict:
    """
    Validate configuration file for common issues.
    
    Args:
        config_path: Path to the configuration JSON file
        
    Returns:
        Validation result with any warnings or errors
    """
    try:
        config = load_config(config_path)
    except FileNotFoundError as e:
        return {"valid": False, "error": str(e), "warnings": []}
    except json.JSONDecodeError as e:
        return {"valid": False, "error": f"Invalid JSON: {e}", "warnings": []}
    
    warnings = []
    
    # Check required sections
    required_sections = ["critical_codes", "chapter_scores", "specialty_scores"]
    for section in required_sections:
        if section not in config:
            warnings.append(f"Missing section: {section}")
    
    # Validate adherence weights sum to 1
    if "adherence_weights" in config:
        weights = config["adherence_weights"]
        total = sum(weights.values())
        if abs(total - 1.0) > 0.01:
            warnings.append(f"Adherence weights sum to {total}, should be 1.0")
    
    # Check for duplicate ICD prefixes
    if "chapter_scores" in config and "mappings" in config["chapter_scores"]:
        prefixes = [m["prefix"] for m in config["chapter_scores"]["mappings"]]
        duplicates = set([p for p in prefixes if prefixes.count(p) > 1])
        if duplicates:
            warnings.append(f"Duplicate ICD prefixes: {duplicates}")
    
    # Check for duplicate specialties
    if "specialty_scores" in config and "mappings" in config["specialty_scores"]:
        specialties = [m["specialty"] for m in config["specialty_scores"]["mappings"]]
        duplicates = set([s for s in specialties if specialties.count(s) > 1])
        if duplicates:
            warnings.append(f"Duplicate specialties: {duplicates}")
    
    # Validate score ranges
    if "chapter_scores" in config and "mappings" in config["chapter_scores"]:
        invalid_scores = [
            m for m in config["chapter_scores"]["mappings"]
            if not (1 <= m.get("score", 0) <= 4)
        ]
        if invalid_scores:
            warnings.append(f"ICD scores should be 1-4, found invalid: {invalid_scores}")
    
    return {
        "valid": len(warnings) == 0 or all("Missing" not in w for w in warnings),
        "warnings": warnings,
        "error": None
    }


def export_current_config(output_path: str = "intervention_config_export.json") -> None:
    """
    Export current module configuration to JSON file.
    
    Useful for creating a baseline config or backing up current settings.
    
    Args:
        output_path: Path to save the exported configuration
    """
    config = {
        "version": "exported",
        "last_updated": "auto-exported",
        "notes": "Exported from current module configuration",
        
        "critical_codes": {
            "description": "ICD-10 codes that trigger HIGH severity override",
            "codes": [{"code": code, "description": ""} for code in ia.ICD_CRITICAL_CODES]
        },
        
        "chapter_scores": {
            "description": "ICD-10 prefix to severity score mapping",
            "mappings": [
                {"prefix": prefix, "score": score, "description": ""}
                for prefix, score in ia.ICD_CHAPTER_SCORES.items()
            ]
        },
        
        "specialty_scores": {
            "description": "Specialty to severity score mapping",
            "mappings": [
                {"specialty": specialty, "score": score}
                for specialty, score in ia.SPECIALTY_SCORES.items()
            ]
        },
        
        "keywords": {
            "critical": ia.CRITICAL_KEYWORDS,
            "surgical": ia.SURGICAL_KEYWORDS,
            "chronic": ia.CHRONIC_KEYWORDS
        },
        
        "thresholds": {
            "clinical_high": 9,
            "clinical_medium": 5,
            "adherence_high": 7.0,
            "adherence_medium": 4.5
        },
        
        "adherence_weights": {
            "anxiety": 0.25,
            "financial": 0.40,
            "compliance": 0.35
        }
    }
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


# =============================================================================
# CLI for config management
# =============================================================================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python intervention_config_loader.py <command> [config_path]")
        print("\nCommands:")
        print("  validate  - Validate configuration file")
        print("  summary   - Show configuration summary")
        print("  export    - Export current module config to JSON")
        print("  apply     - Load and apply configuration")
        sys.exit(1)
    
    command = sys.argv[1]
    config_path = sys.argv[2] if len(sys.argv) > 2 else "intervention_config.json"
    
    if command == "validate":
        result = validate_config(config_path)
        print(f"Valid: {result['valid']}")
        if result['warnings']:
            print("Warnings:")
            for w in result['warnings']:
                print(f"  - {w}")
        if result['error']:
            print(f"Error: {result['error']}")
    
    elif command == "summary":
        try:
            summary = get_config_summary(config_path)
            print(f"Version: {summary['version']}")
            print(f"Last Updated: {summary['last_updated']}")
            print(f"Updated By: {summary['updated_by']}")
            print("\nCounts:")
            for key, value in summary.get('counts', {}).items():
                print(f"  {key}: {value}")
            if 'thresholds' in summary:
                print("\nThresholds:")
                for key, value in summary['thresholds'].items():
                    print(f"  {key}: {value}")
        except Exception as e:
            print(f"Error: {e}")
    
    elif command == "export":
        output_path = sys.argv[2] if len(sys.argv) > 2 else "intervention_config_export.json"
        export_current_config(output_path)
        print(f"Configuration exported to: {output_path}")
    
    elif command == "apply":
        try:
            result = load_and_apply_config(config_path)
            print(f"Applied configuration version: {result['version']}")
            print("Changes applied:")
            for key, applied in result['changes'].items():
                status = "✓" if applied else "✗"
                print(f"  {status} {key}")
        except Exception as e:
            print(f"Error: {e}")
    
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
