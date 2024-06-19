import sys,json,re,time,warnings,math,colorsys,os,contextlib
import pandas as pd
import seaborn as sns
import anndata as ad
import scanpy as sc
import matplotlib.pyplot as plt
import base64
from io import BytesIO
import fastcluster as fc
from scipy.cluster import hierarchy
from difflib import SequenceMatcher
import PyComplexHeatmap as pch
warnings.simplefilter("ignore", UserWarning)
# Rscript ../complexHeatmap.R ttt.csv ZYG11B,OLFM4,PCNA,GSTA1 Expression Celltype,disease 6 8 Reds 1 1 png 2 300 F Yes
def main():
  if len(sys.argv)==1:
    data = json.load(sys.stdin)
  else:
    with open(sys.argv[1],'r') as f:
      data = json.load(f)
  taskRes = distributeTask(data['plot'])(data)

def errorTask(data):
  raise ValueError('Error task!')
def distributeTask(aTask):
  return {
    'violin': complexViolin,
    'dotplot': twofactorDotplot,
    'embedding': reductionPlot,
    'stackbar':stackBar,
    'heatmap':complexHeatmap
  }.get(aTask,errorTask)
def is_numeric(var):
  try:
    float(var)  # Convert to float (handles integers and floats)
    return True
  except ValueError:
    return False
def isOptionDefined(data,k):
  return (data['options'].get(k) is not None and (is_numeric(data['options'][k]) or len(data['options'][k])>0))
def get_n_distinct_colors(n,lightness=0.5,saturation=0.9,cName=None):
  if cName is None:
    return [colorsys.hls_to_rgb(i/n, lightness, saturation) for i in range(n)]
  else:
    cmap=plt.get_cmap(cName)
    return([cmap(i) for i in range(n)])
def toHTML(fig,data):
  st = time.time()
  imgD = iostreamFig(fig,data['options']['img_format'])
  imgID=""
  if len(data['options']['img_id'])>0:
    imgID='id="%s" '%data['options']['img_id']
  imgFormat = re.sub("svg","svg+xml",data['options']['img_format'])
  if data['options']['img_html']:
    print("toHtml: %.2f"%(time.time()-st))
    print('<html><body><img %s src="data:image/%s;base64,%s" width="100%%" height="auto"/></body></html>'%(imgID,imgFormat,imgD))
  else:
    print('data:image/%s;base64,%s'%(imgFormat,imgD))
def iostreamFig(fig,img_format):
  figD = BytesIO()
  fig.savefig(figD,bbox_inches="tight",
    format=img_format)
  imgD = base64.encodebytes(figD.getvalue()).decode("utf-8")
  figD.close()
  if 'matplotlib' in str(type(fig)):
    plt.close(fig)#'all'
  return imgD
def getData(data,dataframe=True):
  D = ad.read_h5ad(data['h5ad'],backed='r')
  if len(data['var_col'])>0 and data['var_col'] in D.var.columns:
    D.var_names = list(D.var[data['var_col']])
  data["genes"] = list(D.var_names[D.var_names.str.lower().isin([s.lower() for s in data['genes']])])
  data['options']["img_format"] = data['options']["img_format"] if data['options'].get("img_format") in ['png','svg'] else "png"
  data['options']["img_width"]=6 if not isOptionDefined(data,"img_width") else data['options']['img_width']
  data['options']["img_height"]=4 if not isOptionDefined(data,"img_height") is None else data['options']['img_height']
  data['options']['cutoff']=0 if not isOptionDefined(data,"cutoff") else data['options']['cutoff']
  data['options']['titlefontsize']=6 if not isOptionDefined(data,"titlefontsize") else data['options']['titlefontsize']
  # only needs when plotting embedding
  reduc=[]
  if data['plot']=='embedding':
    reducName = []
    for one in data['reductions']:
      s=0.5
      selK=None
      for k in D.obsm.keys():
        if SequenceMatcher(None,one.lower(),k.lower()).ratio()>s:
          s=SequenceMatcher(None,one.lower(),k.lower()).ratio()
          selK=k
      if selK is not None and not selK in reducName:
        reducName += [selK]
        reduc += [(selK,0),(selK,1)]
    if len(reducName)==0:
      raise ValueError('No matching reduction/embedding!')
    data['reductions'] = reducName
  #filter cells by annotation selections
  selC = [True] * D.shape[0]
  for one in data["groups"]:
    if len(data["groups"][one])>0:
      delGrp = [re.sub("^-","",_) for _ in data['groups'][one] if _.startswith('-')]
      if len(delGrp)>0:
        selC = selC & ~D.obs[one].isin(delGrp)
      else:
        selC = selC & D.obs[one].isin(data["groups"][one])
  if dataframe:
    df = sc.get.obs_df(D[selC],data['genes']+list(data["groups"].keys()))
    if len(reduc)>0:
      df = df.merge(sc.get.obs_df(D,obsm_keys=reduc),how="left",left_index=True,right_index=True)
    return df
  return D[selC]

def complexViolin(data):
  if len(data["genes"])<1 or len(data["groups"])<1:
    raise ValueError('Missing genes or annotations!')
  st=time.time()
  recordT = {}
  df = getData(data)
  recordT["Get data"]=time.time()-st
  
  w=data['options']["img_width"]
  h=data['options']["img_height"]
  genes=data['genes']
  grps=list(data['groups'].keys())
  gN = len(genes)
  fig, axes = plt.subplots(gN, 1, figsize=(w, h*gN), sharey='row')
  if gN==1:
    axes = [axes]
  for i in range(gN):
    subDF = df
    strTitle = "Total of %d cells" %df.shape[0]
    if data['options']['cutoff']>0:
      subDF = df[(df[genes[i]]>data['options']['cutoff']).values]
      strTitle="%d out of selected %d cells passed the expression filter %.2f"%(subDF.shape[0],df.shape[0],data['options']['cutoff'])
    sns.violinplot(x=grps[0],y=genes[i],ax=axes[i],
      data=subDF,cut=0,
      palette="bright" if not isOptionDefined(data,"palette") else data['options']['palette'],
      #fill=False,inner_kws={"alpha":0.5}, seaborn v0.13.0
      hue=None if len(grps)<2 else grps[1])
    if isOptionDefined(data,"dotsize"):
      dotColor='#000' if not isOptionDefined(data,"dotcolor") else data['options']['dotcolor']
      sns.stripplot(x=grps[0],y=genes[i],ax=axes[i],legend=False,
        data=subDF,size=data['options']["dotsize"],
        palette=[dotColor] if len(grps)<2 else [dotColor]*df[grps[1]].nunique(),
        dodge=False if len(grps)<2 else True,
        hue=None if len(grps)<2 else grps[1])
    axes[i].set_title(strTitle,loc="left",fontdict={'fontsize':data['options']['titlefontsize']})
    if i<(len(genes)-1):
      axes[i].get_xaxis().set_visible(False)
    else:
      plt.setp(axes[i].get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor")
    if len(grps)>1:
      if i==0:
        axes[i].legend(loc='lower right', bbox_to_anchor=(1, 1),
          ncol=1 if len(grps)<2 else df[grps[1]].nunique())
      else:
        axes[i].get_legend().remove()
  recordT["Plot"]=time.time()-st
  if data['options']['img_html']:
    print(pd.DataFrame(recordT,index=["Time"]).transpose())
  #plt.savefig('f.pdf',bbox_inches="tight")
  return(toHTML(fig,data))
def twofactorDotplot(data):
  if len(data["genes"])<1 or len(data["groups"])<1:
    raise ValueError('Missing genes or annotations!')
  df = getData(data)
  w=data['options']["img_width"]
  h=data['options']["img_height"]
  grps=list(data['groups'].keys())
  genes=data['genes']

  D=ad.AnnData(X=df[genes],obs=df[grps])
  strGrp=grps[0]
  if len(grps)>1:
    strGrp = "_".join(grps[:2])
    D.obs[strGrp] = D.obs.apply(lambda x: "_".join(x[grps[:2]]),axis=1)
  strTitle = "%d selected cells"%df.shape[0]
  if data['options']['cutoff']>0:
    strTitle = "%d selected cells with expression cutoff %.2f"%(df.shape[0],data['options']['cutoff'])
  dp=sc.pl.dotplot(D,genes,groupby=strGrp,figsize=(w,h),
    expression_cutoff=data['options']['cutoff'],mean_only_expressed=True,
    return_fig=True)
  dp = (dp.add_totals(size=1.2).
    legend(show_size_legend=True). #,width=float(data['legendW'])
    style(cmap="Reds" if not isOptionDefined(data,'color_map') else data['options']['color_map'],
      dot_edge_color='black', dot_edge_lw=0.5, size_exponent=1.5))
  fig = dp.show(True)['mainplot_ax'].figure
  if len(grps)>1:
    n = df[grps[1]].nunique()
    for i in range(df[grps[0]].nunique()):
      if i==0:
        fig.axes[0].set_title(strTitle,loc="left",fontdict={'fontsize':data['options']['titlefontsize']})
      else:
        fig.axes[0].axhline(y=i*n,color="#0002",linestyle="--")
  return(toHTML(fig,data))
def reductionPlot(data):
  if len(data["reductions"])<1 or len(data["genes"])<1 or len(data["groups"])<1:
    raise ValueError('Missing gene or annotations or reduction/embedding!')
  df = getData(data)
  w=data['options']["img_width"]
  h=data['options']["img_height"]
  grps=list(data['groups'].keys())
  genes=data['genes']
  obsm={}
  for one in data['reductions']:
    obsm[one]=df[["%s-0"%one,"%s-1"%one]].to_numpy()
  
  D=ad.AnnData(X=df[genes],obs=df[grps],obsm=obsm)
  dotsize=120000/D.shape[0]
  subSize = 4
  groupN = len(grps)
  geneN = len(genes)
  ncol = 4 if groupN==1 else df[grps[1]].nunique()
  nrow = groupN + geneN if groupN>1 else groupN+math.ceil(geneN/ncol)
  fig = plt.figure(figsize=(ncol*subSize,subSize*nrow))
  gs = fig.add_gridspec(nrow,ncol,wspace=0.2)
  oneReduc = re.sub("^X_","",data['reductions'][0])
  for i in range(groupN):
    ix = groupN-i-1
    ax = sc.pl.embedding(D,oneReduc,color=grps[ix],ax=fig.add_subplot(gs[i,0]),
      show=False,
      palette=None if not isOptionDefined(data,'palette') else data['options']["palette"])
    ax.legend(ncol=math.ceil(df[grps[ix]].nunique()/10),loc=6,bbox_to_anchor=(1,0.5),
      frameon=False,fontsize=8-df[grps[ix]].nunique()/20)
    ax.set_xlabel('%s 1'%oneReduc)
    ax.set_ylabel('%s 2'%oneReduc)
  if groupN==1:
    for i in geneN:
      x = int(i/ncol)+groupN
      y = i % ncol
      ax = sc.pl.embedding(D,oneReduc,color=genes[i],ax=fig.add_subplot(gs[x,y]),show=False,size=dotsize)
      ax.set_xlabel('%s 1'%oneReduc)
      ax.set_ylabel('%s 2'%oneReduc)
  else:
    splitNames = list(df[grps[1]].unique())
    for i in range(geneN):
      for j in range(len(splitNames)):
        x = groupN + i
        y = j
        
        ax = sc.pl.embedding(D,oneReduc,ax=fig.add_subplot(gs[x,y]),show=False,size=dotsize)
        ax = sc.pl.embedding(D[D.obs[grps[1]]==splitNames[j]],oneReduc,color=genes[i],
          color_map="viridis" if not isOptionDefined(data,'color_map') else data['options']["color_map"],
          vmin=df[genes[i]].min(),vmax=df[genes[i]].max(),ax=ax,show=False,
          size=dotsize,
          title='{} in {}'.format(genes[i],splitNames[j]))
        ax.set_xlabel('%s 1'%oneReduc)
        ax.set_ylabel('%s 2'%oneReduc)
  fig.suptitle("%d selected cells"%df.shape[0],x=0.9,y=0.9,ha="right",va="top",
    fontsize=data['options']['titlefontsize'])
  return(toHTML(fig,data))
def stackBar(data):
  if len(data["groups"])<2:
    raise ValueError('At least 2 annotation groups are required!')
  df = getData(data)
  strTitle = "%d selected cells"%df.shape[0]
  w=data['options']["img_width"]
  h=data['options']["img_height"]
  grps=list(data['groups'].keys())
  x = list(df[grps[1]].unique()) if len(data["groups"][grps[1]])==0 else data["groups"][grps[1]]
  df = (df[grps[:2]].value_counts().to_frame("count").reset_index().
    pivot_table(index=grps[0],columns=grps[1],values="count"))
  fig = plt.figure(figsize=(w,h))
  if data["options"].get("yscale") is not None and data["options"]["yscale"]=="proportion":
    df = df.apply(lambda x: x/x.sum())
    plt.ylabel("Proportion")
  else:
    plt.ylabel("Count")
  plt.xlabel(grps[1])
  color=get_n_distinct_colors(df.shape[0],cName=data['options']["palette"] if isOptionDefined(data,"palette") else None)
  for i in range(df.shape[0]):
    plt.bar(x,df.iloc[i,:][x],color=color[i],
      bottom=df.iloc[:i,:][x].sum())
  plt.legend(df.index,loc=4,bbox_to_anchor=(1,1),
    ncol=math.ceil(df.shape[0]/10),
    fontsize=8-df.shape[0]/20)
  fig.axes[0].set_title(strTitle,
    loc="left",fontdict={'fontsize':data['options']['titlefontsize']})
  return(toHTML(plt,data))
def complexHeatmap(data):
  if len(data["genes"])<1:
    raise ValueError('Missing gene!')
  df = getData(data)
  w=data['options']["img_width"]
  h=data['options']["img_height"]
  grps=list(data['groups'].keys())
  genes = data["genes"]
  selN = df.shape[0]
  df = df[df[genes].apply(lambda x: max(x)>data["options"]["cutoff"],axis=1)]
  heat_scale=None
  heat_title="Expression"
  if data["options"].get("heat_scale") is not None and data["options"]["heat_scale"]=="z-score":
    heat_scale=0
    heat_title="Row Z-score"
  if data["options"].get("cell_order") is None or data["options"]["cell_order"]=="groups":
    df = df.sort_values(list(data["groups"].keys()))
  elif data["options"]["cell_order"]=="expression":
    ix = hierarchy.leaves_list(fc.linkage_vector(df[genes],method="ward"))
    df = df.iloc[ix,]
  if data["options"].get("palette") is not None and len(data["options"]["palette"])>0:
    cmap=data["options"]["palette"]
    colors=None
  else:
    cmap='auto'
    colors={_:dict(zip(df[_].unique(),get_n_distinct_colors(df[_].nunique()))) for _ in grps}
  
  fig = plt.figure(figsize=(w, h))
  with open(os.devnull, "w") as f, contextlib.redirect_stdout(f):
    cm = pch.ClusterMapPlotter(
        data=df[genes],z_score=heat_scale,
        label=heat_title,cmap="jet" if not isOptionDefined(data,"color_map") else data['options']["color_map"],
        left_annotation=pch.HeatmapAnnotation(df[grps],cmap=cmap,colors=colors,axis=0),
        show_rownames=False,show_colnames=True,
        row_dendrogram=False,col_dendrogram=False,
        col_cluster=False,row_cluster=False,
        #row_cluster_method="complete",col_cluster_method="complete",
        rasterized=True,legend=True,legend_anchor='ax_heatmap',
        verbose=0)
  fig.axes[1].set_title("%d of %d selected cells passed expression threshold %.2f"%(df.shape[0],selN,data["options"]["cutoff"]),
    loc="left",fontdict={'fontsize':data['options']['titlefontsize']})
  return(toHTML(plt,data))
main()
# cat ../testVIP/violin.json | python -u plotH5ad.py
# python -u ./plotH5ad.py ../testVIP/violin.json
