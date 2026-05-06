def calculate_expertise(pas: float, ds: float, w_prev: float, w_diag: float) -> float:
    """
    Calculates the weighted expertise score.
    E = (PAS * w_prev) + (DS * w_diag)
    """
    return (pas * w_prev) + (ds * w_diag)

def refine_vark(vark: dict, engagement_type: str, intensity: float = 0.05) -> dict:
    """
    Refines the VARK vector based on engagement telemetry.
    vark: {'v': float, 'a': float, 'r': float, 'k': float}
    engagement_type: 'v', 'a', 'r', or 'k'
    """
    if engagement_type not in vark:
        return vark
    
    # Increase the engaged modality
    vark[engagement_type] += intensity
    
    # Normalize to keep sum = 1.0
    total = sum(vark.values())
    for key in vark:
        vark[key] /= total
        
    return vark

def get_recommended_modality(vark: dict, failed_modalities: list = None) -> str:
    """
    Returns the modality with the highest vector value that hasn't failed.
    """
    if failed_modalities is None:
        failed_modalities = []
        
    sorted_modalities = sorted(vark.items(), key=lambda x: x[1], reverse=True)
    
    for modality, score in sorted_modalities:
        if modality not in failed_modalities:
            return modality
            
    # If all failed, return the one with the highest score anyway (or implement scaffolding)
    return sorted_modalities[0][0]

def check_mastery(score: float, threshold: float = 90.0) -> bool:
    """
    Checks if the student has met the expertise gate.
    """
    return score >= threshold
