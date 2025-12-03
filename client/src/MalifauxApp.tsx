import React, { useState, useMemo, useEffect } from 'react';
import { 
  Search, 
  Database, 
  X, 
  Upload, 
  Save, 
  RefreshCw,
  Loader2,
  Shield, 
  Zap, 
  Move, 
  Maximize,
  Minimize,
  Swords,
  ExternalLink,
  Heart,
  Expand,
  AlertTriangle,
  Download,
  Filter,
  ChevronUp,
  ChevronDown,
  Layers,
  Users,
  User,
  Flag,
  Tag,
  ArrowUp,
  ArrowDown,
  Gem // Ensure Gem is imported for the soulstone icon
} from 'lucide-react';

const DATA_URL = "malifaux_data.json";


// --- CLIENT SIDE NAME CLEANER ---
// Forces clean names even if the data extractor leaves artifacts
const BAD_PREFIXES = new Set([
  "M4E", "CARD", "STAT", "CREW", "UPGRADE", "UNIT", "VERSATILE", "REFERENCE",
  "ARC", "GLD", "RES", "NVB", "OUT", "BYU", "TT", "EXS", "BOH",
  "GUILD", "RESURRECTIONIST", "RESURRECTIONISTS", "ARCANIST", "ARCANISTS", 
  "NEVERBORN", "OUTCAST", "OUTCASTS", "BAYOU", "TEN", "THUNDERS", "EXPLORER", 
  "EXPLORERS", "SOCIETY", "DEAD", "MAN", "MANS", "HAND",
  "ACADEMIC", "AMALGAM", "AMPERSAND", "ANCESTOR", "ANGLER", "APEX", "AUGMENTED", 
  "BANDIT", "BROOD", "BYGONE", "CADMUS", "CAVALIER", "CHIMERA", "DECEMBER", "DUA", 
  "ELITE", "EVS", "EXPERIMENTAL", "FAE", "FAMILY", "FORGOTTEN", "FOUNDRY", "FREIKORPS", 
  "FRONTIER", "HONEYPOT", "INFAMOUS", "JOURNALIST", "KIN", "LAST", "BLOSSOM", 
  "MARSHAL", "MERCENARY", "MONK", "MSU", "NIGHTMARE", "OBLITERATION", "ONI", 
  "PERFORMER", "PLAGUE", "QI", "GONG", "REDCHAPEL", "RETURNED", "REVENANT", 
  "SAVAGE", "SEEKER", "SOOEY", "SWAMPFIEND", "SYNDICATE", "TORMENTED", "TRANSMORTIS", 
  "TRICKSY", "URAMI", "WASTREL", "WILDFIRE", "WITCH", "WITNESS", "WOE",
  "WIZZ", "BANG", "TRI", "CHI"
]);

const cleanDisplayName = (rawName) => {
  if (!rawName) return "Unknown Model";
  
  // 1. Split into words
  const words = rawName.replace(/_/g, ' ').split(/\s+/);
  
  // 2. Eat prefixes from the left
  let startIndex = 0;
  for (let i = 0; i < words.length; i++) {
    const word = words[i].toUpperCase().replace(/[^A-Z0-9]/g, ''); 
    
    // Protect Specific Names from being stripped if they happen to match a keyword
    if (["BIG", "RED", "PALE", "DARK", "MODEL", "HUNTER", "MONSTER", "VOID"].includes(word)) break;

    if (BAD_PREFIXES.has(word)) {
      startIndex = i + 1;
    } else {
      break;
    }
  }
  
  // 3. Join remaining words
  const finalName = words.slice(startIndex).join(' ');
  return finalName || rawName;
};

// --- Utility: PNG URL Guesser ---
const getPngUrl = (url) => {
  if (!url) return null;
  if (url.toLowerCase().endsWith('.pdf')) {
    return url.replace(/\.pdf$/i, '.png');
  }
  return url;
};

// --- Utility: Card Type Icons/Colors ---
const getTypeConfig = (type) => {
  const safeType = typeof type === 'string' ? type : 'Model';
  switch(safeType) {
    case 'Crew': return { label: 'C', color: 'bg-purple-600 text-white border-purple-400' };
    case 'Upgrade': return { label: 'U', color: 'bg-amber-600 text-white border-amber-400' };
    default: return { label: 'M', color: 'bg-blue-600 text-white border-blue-400' };
  }
};

// --- Utility: Faction Colors ---
const getFactionColor = (faction) => {
  return 'bg-slate-700 text-slate-200 border-slate-500';
};

// --- Stat Box Component ---
const StatBox = ({ label, value, icon: Icon, color, onClick, isActive = true }) => {
  // If the value is 0 for non-Hp stats, we skip rendering it.
  if (label !== 'Hp' && (value === undefined || value === null || value === 0)) return null;
  
  return (
    <button 
      onClick={(e) => {
        if (onClick) {
          e.stopPropagation();
          onClick();
        }
      }}
      className={`flex items-center justify-center gap-1.5 px-2 py-1 rounded border border-slate-800/50 bg-slate-900/40 hover:bg-slate-800 hover:border-slate-600 transition-all cursor-pointer active:scale-95 w-full group ${!isActive ? 'opacity-50 grayscale' : ''}`}
      title={`Filter by ${label} ${value}`}
    >
      {Icon && <Icon size={12} className={`opacity-70 group-hover:opacity-100 transition-opacity ${color.replace('text-', 'text-')}`} />}
      <span className={`text-xs font-bold font-mono ${color}`}>{String(value)}</span>
    </button>
  );
};

// --- Card Component ---
const SimpleCard = ({ card, onClick, onFactionClick, onSubFactionClick, onTypeClick, onStatClick }) => {
  const [imgError, setImgError] = useState(false);
  const thumbnailSrc = useMemo(() => getPngUrl(card.imageUrl), [card.imageUrl]);

  const stats = card.stats || {};
  // Check if any standard stat or health exists to show the footer
  const hasStats = (stats.sp > 0) || (stats.df > 0) || (stats.wp > 0) || (card.health > 0);
  
  const displayName = useMemo(() => cleanDisplayName(typeof card.name === 'string' ? card.name : 'Unknown Model'), [card.name]);
  const displayCost = (typeof card.cost === 'number' || typeof card.cost === 'string') ? card.cost : 0;
  const displayType = typeof card.type === 'string' ? card.type : 'Model';
  const displayFaction = typeof card.faction === 'string' ? card.faction : null;
  const displaySubFaction = typeof card.subfaction === 'string' && card.subfaction !== "" ? card.subfaction : null;

  const typeConfig = getTypeConfig(displayType);
  const TypeIcon = typeConfig.icon;

  // Only show base size if it's interesting (not 30mm)
  const showBase = card.base && card.base > 30;
  
  // Soulstone Logic: Use the explicit field if available
  const hasSoulstone = card.soulstone !== undefined ? card.soulstone : false;

  return (
    <div 
      onClick={onClick}
      className="bg-slate-900 rounded-lg overflow-hidden border border-slate-800 shadow-xl flex flex-col h-full group hover:border-amber-600 transition-all hover:-translate-y-1 relative cursor-pointer"
    >
      {/* Header */}
      <div className="bg-slate-950 p-2 px-3 flex justify-between items-start border-b border-slate-800 relative z-10">
        <div className="pr-2 flex-1">
            <h3 className="font-bold text-slate-100 text-sm leading-tight line-clamp-2" title={displayName}>{displayName}</h3>
        </div>
        
        {/* Top Right Badges + Cost */}
        <div className="flex items-center gap-1 flex-shrink-0 ml-2">
           {/* Keyword Badge (Sub-Faction) - First char */}
           {displaySubFaction && (
              <button 
                onClick={(e) => { e.stopPropagation(); onSubFactionClick(displaySubFaction); }} 
                className="w-6 h-6 flex items-center justify-center bg-emerald-700 text-white text-xs font-bold rounded border border-emerald-500 hover:bg-emerald-600 transition-colors"
                title={`Keyword: ${displaySubFaction}`}
              >
                {displaySubFaction.charAt(0).toUpperCase()}
              </button>
           )}

           {/* Faction Badge - First char */}
           {displayFaction && (
              <button 
                onClick={(e) => { e.stopPropagation(); onFactionClick(displayFaction); }} 
                className={`w-6 h-6 flex items-center justify-center text-xs font-bold rounded border hover:brightness-110 transition-colors ${getFactionColor(displayFaction)}`}
                title={`Faction: ${displayFaction}`}
              >
                {displayFaction.charAt(0).toUpperCase()}
              </button>
           )}

           {/* Model Type Badge - M/C/U */}
           <button 
              onClick={(e) => { e.stopPropagation(); onTypeClick(displayType); }} 
              className={`w-6 h-6 flex items-center justify-center text-xs font-bold rounded border hover:brightness-110 transition-colors ${typeConfig.color}`}
              title={`Type: ${displayType}`}
           >
              {typeConfig.label}
           </button>

           {/* Cost */}
           {displayCost > 0 && (
              <div className="w-7 h-7 flex items-center justify-center bg-slate-900 border border-slate-700 rounded text-amber-500 font-serif font-bold text-base ml-1">
                 {String(displayCost)}
              </div>
           )}
        </div>
      </div>

      {/* Image Area */}
      <div className="w-full aspect-[63/88] bg-slate-950 relative overflow-hidden border-b border-slate-800 group">
        {thumbnailSrc && !imgError ? (
          <img 
            src={thumbnailSrc} 
            alt={displayName} 
            className="w-full h-full object-contain object-top transition-transform duration-700 ease-out origin-top scale-100 group-hover:scale-125" 
            loading="lazy" 
            onError={() => setImgError(true)} 
          />
        ) : (
          <div className="w-full h-full flex flex-col items-center justify-center text-slate-700 p-4 text-center">
            <Swords size={48} className="mb-2 opacity-20"/>
            <span className="text-xs">Preview Unavailable</span>
          </div>
        )}
      </div>

      {/* Stats Footer */}
      {hasStats ? (
        <div className="bg-slate-950 px-2 py-2 mt-auto border-t border-slate-800">
          <div className="grid grid-cols-6 gap-1 text-sm font-mono font-bold text-slate-200">
            <StatBox label="Df" value={stats.df} icon={Shield} color="text-blue-400" onClick={() => onStatClick('df', stats.df)} />
            <StatBox label="Sp" value={stats.sp} icon={Move} color="text-green-400" onClick={() => onStatClick('sp', stats.sp)} />
            <StatBox label="Wp" value={stats.wp} icon={Zap} color="text-purple-400" onClick={() => onStatClick('wp', stats.wp)} />
            <StatBox label="Sz" value={stats.sz} icon={Maximize} color="text-slate-400" onClick={() => onStatClick('sz', stats.sz)} />
            
            {/* Health */}
            <StatBox label="Hp" value={card.health || 0} icon={Heart} color="text-red-500" onClick={() => onStatClick('hp', card.health)} />
            
            {/* Soulstone */}
            <StatBox 
                label="SS" 
                value={hasSoulstone ? "Y" : "N"} 
                icon={Gem} 
                color={hasSoulstone ? "text-purple-400" : "text-slate-600"} 
                isActive={hasSoulstone}
                onClick={() => onStatClick('ss', hasSoulstone ? 1 : 0)}
            />
          </div>
        </div>
      ) : (
        <div className="bg-slate-950 p-3 mt-auto flex items-center justify-center text-[10px] text-slate-600 font-medium uppercase tracking-wider border-t border-slate-800">
           {displayType === 'Model' ? 'Stats Unavailable' : displayType}
        </div>
      )}
    </div>
  );
};

// --- Main App ---
export default function MalifauxApp() {
  const [cards, setCards] = useState([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(null);
  const [view, setView] = useState("grid");
  const [searchTerm, setSearchTerm] = useState("");
  const [showFilters, setShowFilters] = useState(false);
  const [showAdmin, setShowAdmin] = useState(false);
  const [jsonInput, setJsonInput] = useState("");
  const [selectedCard, setSelectedCard] = useState(null);

  const [filters, setFilters] = useState({
    type: "All", 
    faction: "All",
    subfaction: "All",
    station: "All",
    costMin: 0,
    costMax: 20,
    spMin: 0,
    dfMin: 0,
    wpMin: 0,
    szMin: 0,
    hpMin: 0,
    baseSize: "All",
    tag: "All",
    summonable: false,
    spExact: null, dfExact: null, wpExact: null, szExact: null, hpExact: null, baseExact: null, ssExact: null,
  });

  const [sortConfig, setSortConfig] = useState({ key: 'name', direction: 'asc' });

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    setLoading(true);
    setFetchError(null);
    try {
      const t = new Date().getTime();
      const res = await fetch(`${DATA_URL}?t=${t}`);
      if (!res.ok) throw new Error("Failed to load");
      const data = await res.json();
      setCards(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error(e);
      setFetchError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSort = (key) => {
    let direction = 'asc';
    if (sortConfig.key === key && sortConfig.direction === 'asc') direction = 'desc';
    setSortConfig({ key, direction });
  };

  const handleFactionClick = (faction) => setFilters(prev => ({ ...prev, faction }));
  const handleSubFactionClick = (subfaction) => setFilters(prev => ({ ...prev, subfaction }));
  const handleTypeClick = (type) => setFilters(prev => ({ ...prev, type }));
  const handleStatClick = (stat, value) => setFilters(prev => ({ ...prev, [`${stat}Exact`]: value }));

  // Derived Lists
  const uniqueFactions = useMemo(() => ["All", ...new Set(cards.map(c => typeof c.faction === 'string' ? c.faction : null).filter(Boolean))], [cards]);
  const uniqueSubFactions = useMemo(() => ["All", ...new Set(cards.map(c => typeof c.subfaction === 'string' ? c.subfaction : null).filter(Boolean))], [cards]);
  const uniqueStations = useMemo(() => ["All", ...new Set(cards.map(c => typeof c.station === 'string' ? c.station : null).filter(Boolean))], [cards]);
  const uniqueTags = useMemo(() => {
    const allTags = cards.flatMap(c => Array.isArray(c.tags) ? c.tags.filter(t => typeof t === 'string') : []);
    return ["All", ...new Set(allTags)].sort();
  }, [cards]);
  const uniqueBaseSizes = useMemo(() => {
    if (!cards.length) return ["All"];
    return ["All", ...new Set(cards.map(c => c.base || 30))].sort((a,b) => a-b)
  }, [cards]);

  const filteredCards = useMemo(() => {
    let queryText = searchTerm.toLowerCase();
    const statQueries = {};
    const statRegex = /\b(cost|sp|df|wp|sz|hp)[:=]?\s*(\d+)\b/g;
    let match;
    while ((match = statRegex.exec(queryText)) !== null) {
        statQueries[match[1]] = parseInt(match[2]);
    }
    queryText = queryText.replace(statRegex, '').trim();

    return cards.filter(card => {
      if (!card) return false;
      const stats = card.stats || {};
      
      const hasSoulstone = card.soulstone !== undefined ? card.soulstone : false;

      if (filters.type !== "All" && (card.type || "Model") !== filters.type) return false;
      
      // Exact Stats
      if (filters.spExact !== null && stats.sp !== filters.spExact) return false;
      if (filters.dfExact !== null && stats.df !== filters.dfExact) return false;
      if (filters.wpExact !== null && stats.wp !== filters.wpExact) return false;
      if (filters.szExact !== null && stats.sz !== filters.szExact) return false;
      if (filters.hpExact !== null && card.health !== filters.hpExact) return false;
      if (filters.baseExact !== null && card.base !== filters.baseExact) return false;
      if (filters.ssExact !== null) {
          if (filters.ssExact === 1 && !hasSoulstone) return false;
          if (filters.ssExact === 0 && hasSoulstone) return false;
      }

      if (statQueries.cost !== undefined && card.cost !== statQueries.cost) return false;
      if (statQueries.sp !== undefined && stats.sp !== statQueries.sp) return false;
      if (statQueries.df !== undefined && stats.df !== statQueries.df) return false;
      if (statQueries.wp !== undefined && stats.wp !== statQueries.wp) return false;
      if (statQueries.sz !== undefined && stats.sz !== statQueries.sz) return false;
      if (statQueries.hp !== undefined && card.health !== statQueries.hp) return false;

      if (queryText) {
        const matchesText = 
          (typeof card.name === 'string' && cleanDisplayName(card.name).toLowerCase().includes(queryText)) ||
          (typeof card.title === 'string' && card.title.toLowerCase().includes(queryText)) ||
          (typeof card.faction === 'string' && card.faction.toLowerCase().includes(queryText)) ||
          (typeof card.subfaction === 'string' && card.subfaction.toLowerCase().includes(queryText)) ||
          (Array.isArray(card.keywords) && card.keywords.some(k => typeof k === 'string' && k.toLowerCase().includes(queryText))) ||
          (typeof card.attacks === 'string' && card.attacks.toLowerCase().includes(queryText));
        if (!matchesText) return false;
      }

      if (filters.faction !== "All" && card.faction !== filters.faction) return false;
      if (filters.subfaction !== "All" && card.subfaction !== filters.subfaction) return false;
      if (filters.station !== "All" && card.station !== filters.station) return false;
      if (card.cost < filters.costMin || card.cost > filters.costMax) return false;
      
      if ((card.type === 'Model' || !card.type) && (
          (stats.sp || 0) < filters.spMin ||
          (stats.df || 0) < filters.dfMin ||
          (stats.wp || 0) < filters.wpMin ||
          (stats.sz || 0) < filters.szMin ||
          (card.health || 0) < filters.hpMin
      )) return false;
      
      if (filters.baseSize !== "All" && card.base?.toString() !== filters.baseSize.toString()) return false;
      if (filters.tag !== "All" && Array.isArray(card.tags) && !card.tags.includes(filters.tag)) return false;

      return true;
    });
  }, [cards, searchTerm, filters]);

  const sortedCards = useMemo(() => {
    return [...filteredCards].sort((a, b) => {
        const dir = sortConfig.direction === 'asc' ? 1 : -1;

        if (sortConfig.key === 'name') {
           const nameA = cleanDisplayName(a.name || '').toLowerCase();
           const nameB = cleanDisplayName(b.name || '').toLowerCase();
           return nameA.localeCompare(nameB) * dir;
        }
        if (sortConfig.key === 'cost') {
            const costA = typeof a.cost === 'number' ? a.cost : 0;
            const costB = typeof b.cost === 'number' ? b.cost : 0;
            return (costA - costB) * dir;
        }
        if (sortConfig.key === 'sp') {
            const spA = a.stats?.sp || 0;
            const spB = b.stats?.sp || 0;
            return (spA - spB) * dir;
        }
        return 0;
    });
  }, [filteredCards, sortConfig]);

  const handleManualImport = () => { try { const parsed = JSON.parse(jsonInput); if (Array.isArray(parsed)) { setCards(parsed); setShowAdmin(false); } } catch (e) { alert("Invalid JSON"); } };
  const safeRenderString = (val) => { if (typeof val === 'string' || typeof val === 'number') return val; return null; };
  const resetFilters = () => { setFilters({ type: "All", faction: "All", subfaction: "All", station: "All", costMin: 0, costMax: 20, spMin: 0, dfMin: 0, wpMin: 0, szMin: 0, hpMin: 0, baseSize: "All", tag: "All", summonable: false, spExact: null, dfExact: null, wpExact: null, szExact: null, hpExact: null, baseExact: null, ssExact: null }); setSearchTerm(""); };
  const removeFilter = (key, resetValue = "All") => { setFilters(prev => ({ ...prev, [key]: resetValue })); };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 font-sans flex flex-col">
      <nav className="bg-slate-900 border-b border-slate-800 sticky top-0 z-50 p-4 shadow-lg shadow-black/50">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3"><div className="bg-amber-600 p-1.5 rounded"><Swords className="text-slate-950" size={20} /></div><h1 className="text-xl font-bold text-slate-100 tracking-tight">Malifaux <span className="text-amber-500">DB</span></h1><button onClick={loadData} className="p-2 hover:text-amber-500 transition-colors" title="Refresh Data"><RefreshCw size={16} className={loading ? "animate-spin" : ""} /></button></div>
          <div className="flex-1 w-full sm:max-w-xl relative group"><Search className="absolute left-3 top-2.5 text-slate-500 group-focus-within:text-amber-500 transition-colors" size={18} /><input type="text" placeholder="Search Name, Ability, or 'df:6'..." className="w-full bg-slate-950 border border-slate-700 rounded-lg pl-10 pr-4 py-2 focus:border-amber-500 focus:ring-1 focus:ring-amber-500 outline-none transition-all placeholder:text-slate-600" value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)}/></div>
          <button onClick={() => setShowFilters(!showFilters)} className={`flex items-center gap-2 px-4 py-2 rounded-lg border font-medium transition-all ${showFilters ? 'bg-amber-500/10 border-amber-500/50 text-amber-400' : 'bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700'}`}><Filter size={18} /> Filters {showFilters ? <ChevronUp size={16} /> : <ChevronDown size={16} />}</button><button onClick={() => setShowAdmin(!showAdmin)} className="text-xs text-slate-500 hover:text-slate-300 font-medium px-2">ADMIN</button>
        </div>
      </nav>

      {(filters.faction !== "All" || filters.subfaction !== "All" || filters.type !== "All" || filters.dfExact !== null || filters.spExact !== null || filters.wpExact !== null || filters.szExact !== null || filters.hpExact !== null || filters.ssExact !== null || searchTerm) && (
         <div className="sticky top-[88px] z-40 bg-slate-950/95 border-b border-slate-800 backdrop-blur-sm px-4 py-2 shadow-md animate-in slide-in-from-top-2">
            <div className="max-w-7xl mx-auto flex flex-wrap gap-2 items-center">
              <span className="text-[10px] font-bold text-slate-500 uppercase mr-1">Active:</span>
              {filters.type !== "All" && (<button onClick={() => removeFilter('type')} className="flex items-center gap-1 px-3 py-1 bg-amber-900/40 text-amber-200 border border-amber-700/50 rounded-full text-xs font-bold hover:bg-amber-900 hover:border-amber-500 transition-all group">Type: {filters.type} <X size={12} className="group-hover:text-white"/></button>)}
              {filters.faction !== "All" && (<button onClick={() => removeFilter('faction')} className="flex items-center gap-1 px-3 py-1 bg-blue-900/40 text-blue-200 border border-blue-700/50 rounded-full text-xs font-bold hover:bg-blue-900 hover:border-blue-500 transition-all group">Faction: {filters.faction} <X size={12} className="group-hover:text-white"/></button>)}
              {filters.subfaction !== "All" && (<button onClick={() => removeFilter('subfaction')} className="flex items-center gap-1 px-3 py-1 bg-emerald-900/40 text-emerald-200 border border-emerald-700/50 rounded-full text-xs font-bold hover:bg-emerald-900 hover:border-emerald-500 transition-all group">Keyword: {filters.subfaction} <X size={12} className="group-hover:text-white"/></button>)}
              {filters.dfExact !== null && (<button onClick={() => removeFilter('dfExact', null)} className="flex items-center gap-1 px-3 py-1 bg-slate-800 text-blue-300 border border-blue-900 rounded-full text-xs font-bold hover:bg-slate-700 transition-all group">Df: {filters.dfExact} <X size={12} className="group-hover:text-white"/></button>)}
              {filters.spExact !== null && (<button onClick={() => removeFilter('spExact', null)} className="flex items-center gap-1 px-3 py-1 bg-slate-800 text-green-300 border border-green-900 rounded-full text-xs font-bold hover:bg-slate-700 transition-all group">Sp: {filters.spExact} <X size={12} className="group-hover:text-white"/></button>)}
              {filters.wpExact !== null && (<button onClick={() => removeFilter('wpExact', null)} className="flex items-center gap-1 px-3 py-1 bg-slate-800 text-purple-300 border border-purple-900 rounded-full text-xs font-bold hover:bg-slate-700 transition-all group">Wp: {filters.wpExact} <X size={12} className="group-hover:text-white"/></button>)}
              {filters.szExact !== null && (<button onClick={() => removeFilter('szExact', null)} className="flex items-center gap-1 px-3 py-1 bg-slate-800 text-slate-300 border border-slate-700 rounded-full text-xs font-bold hover:bg-slate-700 transition-all group">Sz: {filters.szExact} <X size={12} className="group-hover:text-white"/></button>)}
              {filters.hpExact !== null && (<button onClick={() => removeFilter('hpExact', null)} className="flex items-center gap-1 px-3 py-1 bg-slate-800 text-red-300 border border-red-700 rounded-full text-xs font-bold hover:bg-slate-700 transition-all group">Hp: {filters.hpExact} <X size={12} className="group-hover:text-white"/></button>)}
              {filters.ssExact !== null && (<button onClick={() => removeFilter('ssExact', null)} className="flex items-center gap-1 px-3 py-1 bg-slate-800 text-purple-300 border border-purple-700 rounded-full text-xs font-bold hover:bg-slate-700 transition-all group">SS: {filters.ssExact ? "Yes" : "No"} <X size={12} className="group-hover:text-white"/></button>)}
              {searchTerm && (<button onClick={() => setSearchTerm("")} className="flex items-center gap-1 px-3 py-1 bg-slate-800 text-slate-300 border border-slate-700 rounded-full text-xs font-bold hover:bg-slate-700 hover:border-slate-500 transition-all group">Search: "{searchTerm}" <X size={12} className="group-hover:text-white"/></button>)}
               <button onClick={resetFilters} className="text-xs text-slate-500 hover:text-amber-500 underline ml-2 font-medium">Clear All</button>
            </div>
         </div>
      )}

      {showAdmin && (
        <div className="bg-slate-900 p-6 border-b border-slate-700 shadow-inner">
          <div className="max-w-2xl mx-auto">
            <h3 className="text-sm font-bold text-slate-400 mb-2 uppercase tracking-wider">Manual Data Override</h3>
            <textarea className="w-full h-32 bg-slate-950 border border-slate-800 rounded-lg p-3 text-xs font-mono mb-3 focus:border-amber-500 outline-none text-slate-300" value={jsonInput} onChange={e => setJsonInput(e.target.value)} placeholder="Paste your JSON data here if GitHub is slow to update..." />
            <div className="flex justify-end"><button onClick={handleManualImport} className="bg-amber-600 hover:bg-amber-500 text-white px-4 py-2 rounded-lg text-sm font-bold flex items-center gap-2 transition-colors"><Upload size={16}/> Load Manual Data</button></div>
          </div>
        </div>
      )}

      <main className="max-w-7xl mx-auto p-6 flex-1 w-full">
        {loading && (<div className="text-center py-32 opacity-70"><Loader2 size={48} className="animate-spin mx-auto text-amber-500 mb-4"/><p className="text-slate-400 font-medium">Fetching fleet data...</p></div>)}
        {fetchError && (<div className="text-center py-10 text-red-400 bg-red-900/20 rounded border border-red-900/50"><AlertTriangle size={32} className="mx-auto mb-2"/><p>Error loading data: {fetchError}</p></div>)}
        {!loading && !fetchError && (
          <div className="flex flex-col md:flex-row gap-6">
             {showFilters && (
              <aside className="w-full md:w-72 flex-shrink-0 space-y-6 bg-slate-900 p-4 rounded-xl border border-slate-800 h-fit sticky top-36 overflow-y-auto max-h-[80vh]">
                <div className="flex items-center justify-between"><h3 className="font-bold text-slate-300 flex items-center gap-2"><Filter size={16} className="text-amber-500"/> Active Filters</h3><button onClick={resetFilters} className="text-xs text-amber-500 hover:underline">Reset All</button></div>
                <div className="space-y-4">
                  <div><label className="text-xs font-semibold text-slate-500 uppercase mb-2 block">Card Type</label><div className="grid grid-cols-2 gap-2">{["All", "Model", "Crew", "Upgrade"].map(t => (<button key={t} onClick={() => setFilters({...filters, type: t})} className={`px-2 py-1.5 text-xs font-medium rounded border transition-all ${filters.type === t ? 'bg-amber-600 border-amber-500 text-white' : 'bg-slate-800 border-slate-700 text-slate-400 hover:bg-slate-700'}`}>{t}</button>))}</div></div>
                  <div><label className="text-xs font-semibold text-slate-500 uppercase mb-2 block">Faction</label><select className="w-full bg-slate-800 border border-slate-700 text-sm rounded-lg p-2 text-slate-200" value={filters.faction} onChange={(e) => setFilters({...filters, faction: e.target.value})}>{uniqueFactions.map(f => <option key={f} value={f}>{f}</option>)}</select></div>
                  <div><label className="text-xs font-semibold text-slate-500 uppercase mb-2 block">Keyword (Sub-Faction)</label><select className="w-full bg-slate-800 border border-slate-700 text-sm rounded-lg p-2 text-slate-200" value={filters.subfaction} onChange={(e) => setFilters({...filters, subfaction: e.target.value})}>{uniqueSubFactions.map(s => <option key={s} value={s}>{s}</option>)}</select></div>
                  {filters.type !== "Upgrade" && filters.type !== "Crew" && (<><div className="grid grid-cols-2 gap-2"><div><label className="text-xs font-semibold text-slate-500 uppercase mb-2 block">Station</label><select className="w-full bg-slate-800 border border-slate-700 text-sm rounded-lg p-2 text-slate-200" value={filters.station} onChange={(e) => setFilters({...filters, station: e.target.value})}>{uniqueStations.map(s => <option key={s} value={s}>{s}</option>)}</select></div><div><label className="text-xs font-semibold text-slate-500 uppercase mb-2 block">Base Size</label><select className="w-full bg-slate-800 border border-slate-700 text-sm rounded-lg p-2 text-slate-200" value={filters.baseSize} onChange={(e) => setFilters({...filters, baseSize: e.target.value})}>{uniqueBaseSizes.map(s => <option key={s} value={s}>{s}mm</option>)}</select></div></div><div className="grid grid-cols-6 gap-1"><div><label className="text-[10px] uppercase text-slate-500 block mb-1">Sp</label><input type="number" className="w-full bg-slate-800 border border-slate-700 rounded p-1 text-sm" value={filters.spMin} onChange={(e) => setFilters({...filters, spMin: parseInt(e.target.value) || 0})} /></div><div><label className="text-[10px] uppercase text-slate-500 block mb-1">Df</label><input type="number" className="w-full bg-slate-800 border border-slate-700 rounded p-1 text-sm" value={filters.dfMin} onChange={(e) => setFilters({...filters, dfMin: parseInt(e.target.value) || 0})} /></div><div><label className="text-[10px] uppercase text-slate-500 block mb-1">Wp</label><input type="number" className="w-full bg-slate-800 border border-slate-700 rounded p-1 text-sm" value={filters.wpMin} onChange={(e) => setFilters({...filters, wpMin: parseInt(e.target.value) || 0})} /></div><div><label className="text-[10px] uppercase text-slate-500 block mb-1">Sz</label><input type="number" className="w-full bg-slate-800 border border-slate-700 rounded p-1 text-sm" value={filters.szMin} onChange={(e) => setFilters({...filters, szMin: parseInt(e.target.value) || 0})} /></div><div><label className="text-[10px] uppercase text-slate-500 block mb-1">Hp</label><input type="number" className="w-full bg-slate-800 border border-slate-700 rounded p-1 text-sm" value={filters.hpMin} onChange={(e) => setFilters({...filters, hpMin: parseInt(e.target.value) || 0})} /></div></div></>)}
                  <div className="grid grid-cols-2 gap-2"><div><label className="text-[10px] uppercase text-slate-500 block mb-1">Min Cost</label><input type="number" className="w-full bg-slate-800 border border-slate-700 rounded p-1 text-sm" value={filters.costMin} onChange={(e) => setFilters({...filters, costMin: parseInt(e.target.value) || 0})} /></div><div><label className="text-[10px] uppercase text-slate-500 block mb-1">Max Cost</label><input type="number" className="w-full bg-slate-800 border border-slate-700 rounded p-1 text-sm" value={filters.costMax} onChange={(e) => setFilters({...filters, costMax: parseInt(e.target.value) || 0})} /></div></div>
                </div>
              </aside>
            )}
            <div className="flex-1">
                <div className="mb-4 text-xs font-bold text-slate-500 uppercase tracking-widest flex justify-between items-end border-b border-slate-800 pb-2">
                    <span>Showing {filteredCards.length} Cards</span>
                    <div className="flex items-center gap-4">
                      <div className="flex gap-1"><span className="mr-2 text-slate-600">Sort:</span>{['name', 'cost'].map(key => (<button key={key} onClick={() => handleSort(key)} className={`px-2 py-0.5 text-[10px] uppercase font-bold rounded border transition-all flex items-center gap-1 ${sortConfig.key === key ? 'bg-slate-700 border-slate-500 text-amber-400' : 'bg-transparent border-slate-800 text-slate-500 hover:border-slate-600'}`}>{key}{sortConfig.key === key && (sortConfig.direction === 'asc' ? <ArrowUp size={10}/> : <ArrowDown size={10}/>)}</button>))}</div>
                    </div>
                </div>
                <div className={view === "grid" ? "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-6" : "flex flex-col gap-2"}>
                    {sortedCards.map((card, idx) => (<SimpleCard key={card.id || idx} card={card} onClick={() => setSelectedCard(card)} onFactionClick={handleFactionClick} onSubFactionClick={handleSubFactionClick} onTypeClick={handleTypeClick} onStatClick={handleStatClick}/>))}
                </div>
            </div>
          </div>
        )}
        {!loading && !fetchError && filteredCards.length === 0 && (
          <div className="text-center py-32 text-slate-500"><Database size={48} className="mx-auto mb-4 opacity-20"/><p className="text-lg">No cards found matching <span className="text-amber-500">"{searchTerm}"</span></p></div>
        )}
      </main>

      {selectedCard && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/90 backdrop-blur-md" onClick={() => setSelectedCard(null)}>
          <div className="bg-slate-900 w-full max-w-5xl h-[90vh] rounded-2xl border border-slate-700 shadow-2xl overflow-hidden flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="bg-slate-950 p-4 border-b border-slate-800 flex justify-between items-center shrink-0">
               <div>
                 <div className="flex items-center gap-2"><h2 className="text-xl font-bold text-slate-100">{typeof selectedCard.name === 'string' ? cleanDisplayName(selectedCard.name) : 'Unknown'}</h2><span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${getTypeConfig(selectedCard.type || 'Model').color.replace('/90', '')}`}>{selectedCard.type || 'Model'}</span></div>
                 {selectedCard.title && typeof selectedCard.title === 'string' && (<p className="text-xs text-amber-500 uppercase tracking-widest font-semibold">{selectedCard.title}</p>)}
                 <div className="flex gap-2 mt-1">{selectedCard.faction && (<span className="text-xs text-blue-400 flex items-center gap-1"><Flag size={10}/> {selectedCard.faction}</span>)}{selectedCard.subfaction && (<span className="text-xs text-emerald-400 flex items-center gap-1"><Tag size={10}/> {selectedCard.subfaction}</span>)}</div>
               </div>
               <div className="flex gap-2">{selectedCard.imageUrl && (<a href={selectedCard.imageUrl} target="_blank" rel="noopener noreferrer" className="px-3 py-2 bg-slate-800 hover:bg-slate-700 rounded-lg transition-colors text-amber-500 text-sm font-medium flex items-center gap-2 border border-slate-700"><Download size={16} /> PDF</a>)}<button onClick={() => setSelectedCard(null)} className="p-2 hover:bg-slate-800 rounded-full transition-colors text-slate-400 hover:text-white"><X size={24} /></button></div>
            </div>
            <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
                <div className="md:w-6/12 bg-slate-950 border-b md:border-b-0 md:border-r border-slate-800 relative flex items-center justify-center p-4 overflow-auto">{getPngUrl(selectedCard.imageUrl) ? (<img src={getPngUrl(selectedCard.imageUrl)} alt={selectedCard.name} className="max-h-full w-auto object-contain rounded shadow-2xl" />) : (<div className="flex flex-col items-center justify-center text-slate-500"><ImageIcon size={64} className="mb-4 opacity-30"/><p>No Card Image Available</p></div>)}</div>
                <div className="md:w-6/12 overflow-y-auto p-6 space-y-8 bg-slate-900">
                    {(!selectedCard.type || selectedCard.type === "Model") && (<div className="flex justify-center gap-4 pb-6 border-b border-slate-800/50"><StatBox label="Df" value={selectedCard.stats?.df} icon={Shield} color="text-blue-400" onClick={() => handleStatClick('df', selectedCard.stats.df)}/><StatBox label="Sp" value={selectedCard.stats?.sp} icon={Move} color="text-green-400" onClick={() => handleStatClick('sp', selectedCard.stats.sp)}/><StatBox label="Wp" value={selectedCard.stats?.wp} icon={Zap} color="text-purple-400" onClick={() => handleStatClick('wp', selectedCard.stats.wp)}/><StatBox label="Sz" value={selectedCard.stats?.sz} icon={Maximize} color="text-slate-300" onClick={() => handleStatClick('sz', selectedCard.stats.sz)}/>
                    <StatBox label="Hp" value={selectedCard.health} icon={Heart} color="text-red-500" onClick={() => handleStatClick('hp', selectedCard.health)} />
                    <StatBox label="SS" value={selectedCard.soulstone ? "Y" : "N"} icon={Gem} color={selectedCard.soulstone ? "text-purple-400" : "text-slate-600"} isActive={selectedCard.soulstone} onClick={() => handleStatClick('ss', selectedCard.soulstone ? 1 : 0)} />
                    <StatBox label="Base" value={selectedCard.base} icon={Expand} color="text-slate-400" onClick={() => handleStatClick('base', selectedCard.base)}/></div>)}
                    <div className="flex flex-wrap justify-center gap-2">{Array.isArray(selectedCard.keywords) && selectedCard.keywords.map(k => { const val = safeRenderString(k); return val ? <Badge key={val} color="blue">{val}</Badge> : null; })}{Array.isArray(selectedCard.characteristics) && selectedCard.characteristics.map(c => { const val = safeRenderString(c); return val ? <Badge key={val} color="purple">{val}</Badge> : null; })}{Array.isArray(selectedCard.tags) && selectedCard.tags.map(t => { const val = safeRenderString(t); return val ? <Badge key={val} color="slate">{val}</Badge> : null; })}</div>
                    {selectedCard.attacks && typeof selectedCard.attacks === 'string' && (<div className="mt-4 p-4 bg-slate-800/50 rounded border border-slate-700/50"><h4 className="text-xs font-bold text-slate-500 uppercase mb-2 flex items-center gap-2"><Swords size={12}/> Searchable Text</h4><p className="text-xs text-slate-400 font-mono whitespace-pre-wrap leading-relaxed opacity-70">{selectedCard.attacks.substring(0, 500) + (selectedCard.attacks.length > 500 ? "..." : "")}</p></div>)}
                    <div className="text-center italic text-slate-600 text-sm pt-4 font-serif border-t border-slate-800/50">Rules Compliant - Malifaux 4E</div>
                </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Helper for badges in modal
const Badge = ({ children, color }) => {
    let colorClass = "bg-slate-800 text-slate-300 border-slate-600";
    if (color === 'blue') colorClass = "bg-blue-900/50 text-blue-200 border-blue-700/50";
    if (color === 'purple') colorClass = "bg-purple-900/50 text-purple-200 border-purple-700/50";
    return (
        <span className={`px-2 py-1 rounded text-[10px] uppercase font-bold border ${colorClass}`}>
            {children}
        </span>
    );
}