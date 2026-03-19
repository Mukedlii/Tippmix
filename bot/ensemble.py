"""
bot/ensemble.py

Ensemble AI - Multiple models voting for better accuracy
Uses Claude + GPT-4o + Gemini for predictions
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional
from collections import Counter

log = logging.getLogger(__name__)


class EnsembleAI:
    """Ensemble prediction using multiple AI models."""

    def __init__(self):
        self.use_ensemble = os.getenv("TIPPMIX_USE_ENSEMBLE", "1") == "1"
        self.models = os.getenv("TIPPMIX_ENSEMBLE_MODELS", "claude,gpt,gemini").split(",")
        self.min_agreement = int(os.getenv("TIPPMIX_ENSEMBLE_MIN_AGREEMENT", "2"))
        
        # Check which models are available
        self.has_claude = bool(os.getenv("ANTHROPIC_API_KEY"))
        self.has_openai = bool(os.getenv("OPENAI_API_KEY"))
        self.has_gemini = bool(os.getenv("GEMINI_API_KEY"))

    def _call_claude(self, dossiers: List[Dict], web_context: str) -> Dict:
        """Call Claude Sonnet for predictions."""
        try:
            from bot.openai_logic import _call_llm
            # Current implementation already uses Claude
            return _call_llm(dossiers, web_context)
        except Exception as e:
            log.error(f"Claude call failed: {e}")
            return {"vip_tips": [], "free_tips": []}

    def _call_gpt(self, dossiers: List[Dict], web_context: str, system_prompt: str) -> Dict:
        """Call OpenAI GPT-4o for predictions."""
        if not self.has_openai:
            return {"vip_tips": [], "free_tips": []}

        try:
            from openai import OpenAI
            import json
            
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            
            prompt = f"Meccs dossziék:\n{json.dumps(dossiers[:30], ensure_ascii=False, indent=2)}\n\n{web_context}"
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",  # Cheaper version
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.25
            )
            
            return json.loads(response.choices[0].message.content or "{}")
            
        except Exception as e:
            log.error(f"GPT call failed: {e}")
            return {"vip_tips": [], "free_tips": []}

    def _call_gemini(self, dossiers: List[Dict], web_context: str, system_prompt: str) -> Dict:
        """Call Google Gemini for predictions."""
        if not self.has_gemini:
            return {"vip_tips": [], "free_tips": []}

        try:
            import google.generativeai as genai
            import json
            
            genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            prompt = f"{system_prompt}\n\nMeccs dossziék:\n{json.dumps(dossiers[:30], ensure_ascii=False, indent=2)}\n\n{web_context}\n\nRespond ONLY with valid JSON."
            
            response = model.generate_content(
                prompt,
                generation_config={
                    'temperature': 0.25,
                    'max_output_tokens': 8192,
                }
            )
            
            text = response.text
            # Strip markdown if present
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
            
            return json.loads(text)
            
        except Exception as e:
            log.error(f"Gemini call failed: {e}")
            return {"vip_tips": [], "free_tips": []}

    def vote_tips(self, all_tips: List[List[Dict]], tier: str = "VIP") -> List[Dict]:
        """
        Vote on tips from multiple models.
        
        Args:
            all_tips: List of tip lists from different models
            tier: VIP or FREE
        
        Returns:
            Consensus tips with vote counts
        """
        # Flatten all tips by fixture_id + selection
        tip_votes = {}
        
        for model_tips in all_tips:
            for tip in model_tips:
                fixture_id = tip.get("fixture_id")
                selection = tip.get("selection", "")
                
                if not fixture_id:
                    continue
                
                key = f"{fixture_id}_{selection}"
                
                if key not in tip_votes:
                    tip_votes[key] = {
                        "tip": tip,
                        "votes": 0,
                        "total_confidence": 0,
                        "models": []
                    }
                
                tip_votes[key]["votes"] += 1
                tip_votes[key]["total_confidence"] += float(tip.get("confidence", 0))
                tip_votes[key]["models"].append(tip.get("model", "unknown"))
        
        # Filter by minimum agreement
        consensus_tips = []
        
        for key, data in tip_votes.items():
            if data["votes"] >= self.min_agreement:
                tip = data["tip"].copy()
                tip["ensemble_votes"] = data["votes"]
                tip["ensemble_models"] = data["models"]
                tip["confidence"] = round(data["total_confidence"] / data["votes"], 2)
                consensus_tips.append(tip)
        
        # Sort by votes then confidence
        consensus_tips.sort(key=lambda x: (x["ensemble_votes"], x["confidence"]), reverse=True)
        
        return consensus_tips

    def get_ensemble_predictions(
        self, 
        dossiers: List[Dict], 
        web_context: str,
        system_prompt: str
    ) -> Dict[str, List[Dict]]:
        """
        Get predictions from all available models and vote.
        
        Returns:
            {
                "vip_tips": [...],
                "free_tips": [...],
                "ensemble_stats": {...}
            }
        """
        if not self.use_ensemble:
            # Fallback to single model (Claude)
            return self._call_claude(dossiers, web_context)
        
        log.info(f"Running ensemble with models: {self.models}")
        
        # Collect predictions from all models
        all_predictions = []
        model_names = []
        
        if "claude" in self.models and self.has_claude:
            log.info("Calling Claude...")
            claude_pred = self._call_claude(dossiers, web_context)
            # Tag model
            for tip in claude_pred.get("vip_tips", []):
                tip["model"] = "claude"
            for tip in claude_pred.get("free_tips", []):
                tip["model"] = "claude"
            all_predictions.append(claude_pred)
            model_names.append("claude")
        
        if "gpt" in self.models and self.has_openai:
            log.info("Calling GPT-4o...")
            gpt_pred = self._call_gpt(dossiers, web_context, system_prompt)
            for tip in gpt_pred.get("vip_tips", []):
                tip["model"] = "gpt"
            for tip in gpt_pred.get("free_tips", []):
                tip["model"] = "gpt"
            all_predictions.append(gpt_pred)
            model_names.append("gpt")
        
        if "gemini" in self.models and self.has_gemini:
            log.info("Calling Gemini...")
            gemini_pred = self._call_gemini(dossiers, web_context, system_prompt)
            for tip in gemini_pred.get("vip_tips", []):
                tip["model"] = "gemini"
            for tip in gemini_pred.get("free_tips", []):
                tip["model"] = "gemini"
            all_predictions.append(gemini_pred)
            model_names.append("gemini")
        
        if not all_predictions:
            log.error("No model predictions available!")
            return {"vip_tips": [], "free_tips": [], "ensemble_stats": {}}
        
        # Vote on VIP tips
        all_vip = [pred.get("vip_tips", []) for pred in all_predictions]
        vip_consensus = self.vote_tips(all_vip, tier="VIP")
        
        # Vote on FREE tips
        all_free = [pred.get("free_tips", []) for pred in all_predictions]
        free_consensus = self.vote_tips(all_free, tier="FREE")
        
        # Stats
        ensemble_stats = {
            "models_used": model_names,
            "total_models": len(all_predictions),
            "min_agreement": self.min_agreement,
            "vip_consensus_count": len(vip_consensus),
            "free_consensus_count": len(free_consensus),
        }
        
        log.info(f"Ensemble complete: {ensemble_stats}")
        
        return {
            "vip_tips": vip_consensus,
            "free_tips": free_consensus,
            "ensemble_stats": ensemble_stats,
        }
