#!/usr/bin/env python
# -*- coding: ASCII -*-

"""

:Author: Martin Kircher
:Contact: Martin.Kircher@eva.mpg.de
:Date: *23.06.2009

"""

import sys,os
from optparse import OptionParser
from optparse import OptionGroup
import gzip
import string
import time
import subprocess

if (len(sys.argv[0]) > 0)  and os.path.isdir(os.getcwd()+"/"+os.path.dirname(sys.argv[0])):
  root_bin = os.path.dirname(os.getcwd()+"/"+sys.argv[0])
elif (len(sys.argv[0]) > 0)  and os.path.isdir(os.path.dirname(sys.argv[0])):
  root_bin = os.path.dirname(sys.argv[0])
else:
  root_bin = os.getcwd()
f=open(root_bin+'/params.py')
c=compile(f.read(), root_bin+'/params.py', "exec")
eval(c)

offset=64 #Solexa quality offset
max_length_soap=40
max_frags_created = 1
table = string.maketrans('.','N')
compSEQ = string.maketrans('CATG','GTAC')

def rev_compl(seq):
  nseq=seq.translate(compSEQ)
  nseq=list(nseq)
  nseq.reverse()
  return "".join(nseq)

def parse_rangestr(rangestr):
  res = []
  fields = rangestr.split(',')
  for elem in fields:
    if "-" in elem:
      se = elem.split('-')
      if len(se) == 2:
        try:
          start = int(se[0])
          end = int(se[1])
          res.extend(range(start,end+1))
        except: return None
      else: return None
    else:
      try:
        pos = int(elem)
        res.append(pos)
      except: return None
  if len(res) == 0: return None
  else:
    res = list(set(res))
    res.sort()
    return res

def read_fasta(filename):
  infile = open(filename)
  seq=""
  header=""
  for line in infile:
    line = line.strip()
    if (line[0] == ">"):
      if (header != "") and (seq != ""):
        yield header,seq
      header = line[1:]
      seq = ""
    else:
      seq+=line
  if (header != ""):
    yield header,seq
  infile.close()
  raise StopIteration

def read_fastq_file(filename):
  infile = open(filename)
  name,seq,qual = "","",""
  count = 0
  for line in infile:
    if line.startswith("@") and ((count == 0) or (count == 3)):
      count=1
      if len(seq) > 0:
        yield name,seq,qual
      name = tuple(line[1:].strip().split(":")[-4:])
      if len(name) != 4:
        print "Unexpected sequence ID:",line.strip()
        raise StopIteration
      seq = ""
      qual = ""
    elif (not line.startswith("+")) and (count == 1):
      seq += line.strip()
    elif line.startswith("+") and (count == 1):
      count=2
    elif (count >= 2):
      qual += line.strip()
      count = 3
    else:
      print "Unexpected line:",line.strip()
      raise StopIteration
  if len(seq) > 0:
    yield name,seq,qual
  infile.close()
  raise StopIteration

def read_qseq_file(filename):
  global table
  infile = open(filename)
  exp_fields = 11
  flane = 2
  ftile = 3
  fx = 4
  fy = 5
  fseq = 8
  fqual = 9
  for line in infile:
    fields = line.split('\t')
    if len(fields) == exp_fields:
      yield (fields[flane],fields[ftile],fields[fx],fields[fy]),fields[fseq].translate(table),fields[fqual]
    else:
      print "Unexpected line",line.rstrip()
      raise StopIteration
  infile.close()
  raise StopIteration

def read_seq_prb_file(filename):
  global offset
  if filename[1] != None: prb = open(filename[1],'r')
  base = open(filename[0],'r')
  cprb = " "
  cbase = " "
  while ((cprb <> []) and (cbase <> [])):
    cbase = base.readline().split()
    if (len(cbase) > 4):
      name=tuple(cbase[:4])
      cbase=cbase[4].translate(table)
      if filename[1] != None: cprb = prb.readline().split("\t")
      prstr=''
      if filename[1] != None:
        for x in cprb:
          prstr+=chr(max(map(int,x.split()))+offset)
      yield name,cbase,prstr
  if filename[1] != None: prb.close()
  base.close()

def write_out_soap_fa(ofilestream,name,seq):
  global max_length_soap
  global max_frags_created
  frags=len(seq)//((len(seq)//max_length_soap)+1)
  count = 1
  while len(seq) > 0:
    if len(seq) <= max_length_soap:
      cseq = seq
      seq = ""
    else:
      cseq = seq[:frags]
      seq = seq[frags:]
    ofilestream.write(">%s#%d\n%s\n"%(name,count,cseq))
    if max_frags_created < count: max_frags_created=count
    count += 1

def eval_soap_output(infilename,outfilename,seq_dict,delta_bases,options):
  outfile = open(outfilename,'w')
  infile = open(infilename,'r')
  count = 0
  line = infile.readline()
  fields = line.split()
  cid = ""
  cnum = -1
  cdata = {}
  while line != "":
    if (cid == ""):
      hfields = fields[0].split("#")
      cid = "#".join(hfields[:-1])
      cnum = int(hfields[-1])
      cdata[cnum] = fields
    else:
      cdata[cnum] = fields

    nextline = infile.readline()
    nextfields = nextline.split()
    try:
      hfields = nextfields[0].split("#")
      nextcid = "#".join(hfields[:-1])
      nextnum = int(hfields[-1])
    except:
      nextcid = ""
      nextnum = -1

    if (nextcid != cid) and (cid != ""):
      cdata[cnum] = fields
      keys = cdata.keys()
      keys.sort()
      consistent = False
      if (len(keys) == 1 and keys[0]==1) and (len(cdata[keys[0]]) > 9):
        fstart = int(cdata[keys[0]][8])-1
        lpos = int(cdata[keys[0]][8])
        lref = cdata[keys[0]][7]
        lstrand = cdata[keys[0]][6]
        total_mmatch = int(cdata[keys[0]][9])
        if lstrand == "-":
          seq = rev_compl(cdata[keys[0]][1])
          lpos -= (delta_bases-len(seq))
          fstart -= (delta_bases-len(seq))
          seq = (delta_bases-len(seq))*"N"+seq
        else:
          seq = cdata[keys[0]][1]
          lpos += len(cdata[keys[0]][1])+(delta_bases-len(seq))
          seq += (delta_bases-len(seq))*"N"
        consistent = True
        seq+=(delta_bases-len(seq))*"N"
        #print cid,cdata[keys[0]][:4]
      elif len(cdata[keys[0]]) > 9:
        fstart = int(cdata[keys[0]][8])-1
        lpos = int(cdata[keys[0]][8])
        lref = cdata[keys[0]][7]
        lstrand = cdata[keys[0]][6]
        total_mmatch = int(cdata[keys[0]][9])
        if lstrand == "-":
          seq = rev_compl(cdata[keys[0]][1])
        else:
          seq = cdata[keys[0]][1]
          lpos += len(cdata[keys[0]][1])
        consistent = True
        for key in keys[1:]:
          if (len(cdata[key]) <= 9) or (lref != cdata[key][7]) or (lstrand != cdata[key][6]):
            consistent = False
            break
          else:
            if (lstrand == '-') and (lpos-len(cdata[key][1]) == int(cdata[key][8])):
              lpos -= len(cdata[key][1])
              seq += rev_compl(cdata[key][1])
              fstart -= len(cdata[key][1])
              total_mmatch += int(cdata[key][9])
            elif (lstrand == '+') and (lpos == int(cdata[key][8])):
              lpos += len(cdata[key][1])
              seq += cdata[key][1]
              total_mmatch += int(cdata[key][9])
            else:
              consistent = False
              #print lpos+1,lref,lstrand,'  vs  ',cdata[key][7],cdata[key][6],cdata[key][8],'  ',key
              break

      if consistent and (lref in seq_dict) and (options.mismatch >= total_mmatch):
        new_seq = seq_dict[lref][fstart:fstart+delta_bases].upper()
        if (len(new_seq) == delta_bases) and (len(seq) == delta_bases):
          if lstrand == "-":
            new_seq = rev_compl(new_seq)
          if options.maskMM:
            seq=seq.upper()
            for ind,base in enumerate(seq):
              if new_seq[ind] != base:
                new_seq=new_seq[:ind]+"N"+new_seq[ind+1:]
          #print "\t".join(cid.split(":")[1:])+"\t"+new_seq
          outfile.write("\t".join(cid.split(":")[1:])+"\t"+new_seq+"\n")
          count += 1
      elif consistent and (lref not in seq_dict):
        print "Error, could not extract sequence for reference",lref
      cdata = {}
      cid = nextcid

    cnum = nextnum
    line = nextline
    fields = nextfields
  infile.close()
  outfile.close()
  return count

#########################
### USER PARAMETER ...
#########################

parser = OptionParser(usage="usage: %prog [options]")
group = OptionGroup(parser, "Bustard","General options describing sequencing data")
group.add_option("-p", "--path", dest="path", help="Path to bustard folder (default .)", default=".")
group.add_option("-e", "--expID", dest="expID", help="Name of experiment to use for sequence names",default="SoapTraining")
group.add_option("-l", "--lanes", dest="lanes", help="Lanes, example: 1,3,4-8 (default 4)",default="4")
group.add_option("-t", "--tiles", dest="tiles", help="Lanes, example: 1-13,100 (default 1-100)",default="1-100")
parser.add_option_group(group)

group = OptionGroup(parser, "Filter/Paired End","Excluding sequences and bases for training")
group.add_option("--start",dest="start",help="First base to include/first base in each read (comma separate)")
group.add_option("--end",dest="end",help="Last base to include/last base in each read (comma separate)")
group.add_option("--numberN", dest="numberN", help="Maximum number of missing bases to be accepted (default 3)",default=3,type="int")

parser.add_option_group(group)

group = OptionGroup(parser, "SOAP","Parameters for SOAP mapping")
group.add_option("-s", "--soap", dest="soap", help="Path to SOAP binary (default "+def_soap_path+")",default=def_soap_path)
group.add_option("-c", "--cores", dest="cores", help="Number of CPU cores for SOAP (default 1)",default=1,type="int")
group.add_option("-r", "--reference", dest="reference", help="Reference genome file",default=def_soap_ref)
group.add_option("-m", "--mismatch", dest="mismatch", help="Number of mismatches allowed (default 5)",default=5,type="int")
group.add_option("--maskMM", dest="maskMM", help="Mask mismatches from SOAP output in training data",action="store_true",default=False)
parser.add_option_group(group)

group = OptionGroup(parser, "Files","Options for final/intermediate output")
group.add_option("-o", "--outfile", dest="outfile", help="Path for output file(s)")
group.add_option("--temp", dest="tmp", help="Path to temporary folder (default "+def_temp+")",default=def_temp)
group.add_option("--keep", dest="keep", help="Keep temporary files for debugging (default OFF)",action="store_true",default=False)
parser.add_option_group(group)

(options, args) = parser.parse_args()

################################
# EVALUATE READ STARTS AND ENDS
################################

reads = 1
tstart = 1
tstart2 = None
tend = None
tend2 = None
if (options.start != None) and ((options.start).count(",") == 1):
  try:
    fields = (options.start).split(",")
    tstart = int(fields[0])
    tstart2 = int(fields[1])
    reads = 2
  except:
    print "Can't evaluate sequence starts:",options.start
    sys.exit()
elif (options.start != None) and ((options.start).count(",") == 0):
  try:
    tstart = int(options.start)
  except:
    print "Can't evaluate sequence start:",options.start
    sys.exit()
elif options.start != None:
  print "Can't evaluate sequence start:",options.start
  sys.exit()

if (options.end != None) and ((options.end).count(",") == 1):
  try:
    fields = (options.end).split(",")
    tend = int(fields[0])
    tend2 = int(fields[1])
    reads = 2
  except:
    print "Can't evaluate sequence starts:",options.end
    sys.exit()
elif (options.end != None) and ((options.end).count(",") == 0):
  try:
    tend = int(options.end)
  except:
    print "Can't evaluate sequence start:",options.end
    sys.exit()
elif options.end != None:
  print "Can't evaluate sequence start:",options.end
  sys.exit()

if tstart > 0: tstart -= 1
else: tstart=0
if tend <= 0: tend = None

if tstart2 > 0: tstart2 -= 1
else: tstart2=0
if tend2 <= 0: tend2 = None

if (reads == 2) and ((tend2 == None) or (tstart2 == None) or (tend == None)):
  print "Need both starts and ends for two reads."
  sys.exit()

print "Using bases",tstart+1,"to",tend,"for SOAP mapping."
if (reads == 2):
  print "Using bases",tstart2+1,"to",tend2,"for SOAP mapping of second read."

if (options.expID == None):
  print "Need an name for the experiment."
  sys.exit()

if (options.soap == None) or not(os.path.isfile(options.soap)):
  print "Need path to SOAP binary."
  sys.exit()

if (options.reference == None) or not(os.path.isfile(options.reference)):
  print "Need path to reference Genome."
  sys.exit()

if (options.tmp == None) or not(os.path.isdir(options.tmp)):
  print "Need path to temporary folder."
  sys.exit()

if (options.path == None) or not(os.path.isdir(options.path)):
  print "Need path to Bustard folder."
  sys.exit()
options.path=options.path.rstrip("/")

if (options.outfile == None):
  print "Need name for training output file."
  sys.exit()

lanes = parse_rangestr(options.lanes)
if lanes == None:
  print "Need a valid range of lanes."
  sys.exit()
print "Using lanes:",lanes

tiles = parse_rangestr(options.tiles)
if tiles == None:
  print "Need a valid range of tiles."
  sys.exit()
print "Using tiles:",tiles

# SHOULD NEVER BE NECCESSARY, BUT YOU NEVER KNOW :)
if tstart2 == None: tstart2=tstart
if tend2 == None: tend2=tend

srange1=str(tstart)+":"+str(tend)
srange2=str(tstart2)+":"+str(tend2)

timestamp = str(time.time())

print ""
outfilename = options.tmp+"/"+timestamp+"_soap_input.txt"
print "Creating temporary file with sequences:",outfilename
outfile = open(outfilename,'w')
if reads == 2:
  outfilename_r2 = options.tmp+"/"+timestamp+"_soap_input_2.txt"
  print "Creating temporary file with sequences:",outfilename_r2
  outfile_r2 = open(outfilename_r2,'w')
else: # SHOULD NEVER BE NECCESSARY
  outfile_r2 = outfile

had_training_sequences = False
for lane in lanes:
  lane = str(lane)
  files = []
  first_read = []
  second_read = []

  for nr in tiles:
    nr = str(nr)
    while len(nr) < 4:
      nr="0"+nr
    if os.path.isfile(options.path+"/s_"+lane+"_1_"+nr+"_qseq.txt"):
      first_read.append(options.path+"/s_"+lane+"_1_"+nr+"_qseq.txt")
    if os.path.isfile(options.path+"/s_"+lane+"_3_"+nr+"_qseq.txt"):
      second_read.append(options.path+"/s_"+lane+"_3_"+nr+"_qseq.txt")
    elif os.path.isfile(options.path+"/s_"+lane+"_2_"+nr+"_qseq.txt"):
      second_read.append(options.path+"/s_"+lane+"_2_"+nr+"_qseq.txt")

    if os.path.isfile(options.path+"/s_"+lane+"_"+nr+"_seq.txt") and os.path.isfile(options.path+"/s_"+lane+"_"+nr+"_prb.txt"):
      first_read.append((options.path+"/s_"+lane+"_"+nr+"_seq.txt",None)) #options.path+"/s_"+lane+"_"+nr+"_prb.txt"
    if os.path.isfile(options.path+"/s_"+lane+"_"+nr+"_seq.txt") and (not os.path.isfile(options.path+"/s_"+lane+"_"+nr+"_prb.txt")):
      first_read.append((options.path+"/s_"+lane+"_"+nr+"_seq.txt",None))

    if os.path.isfile(options.path+"/s_"+lane+"_"+nr+".fastq"):
      first_read.append(options.path+"/s_"+lane+"_"+nr+".fastq")
    if os.path.isfile(options.path+"/s_"+lane+"_1_"+nr+".fastq"):
      first_read.append(options.path+"/s_"+lane+"_1_"+nr+".fastq")
    if os.path.isfile(options.path+"/s_"+lane+"_3_"+nr+".fastq"):
      second_read.append(options.path+"/s_"+lane+"_3_"+nr+".fastq")
    elif os.path.isfile(options.path+"/s_"+lane+"_2_"+nr+".fastq"):
      second_read.append(options.path+"/s_"+lane+"_2_"+nr+".fastq")

  start2ndread=None
  second_in_first = ((len(second_read) == 0) and (reads == 2))
  file_reader = None
  for filename in first_read:
    had_training_sequences = True
    if len(filename) != 2 and filename.endswith("qseq.txt"):
      file_reader = read_qseq_file
    elif len(filename) != 2 and filename.endswith("fastq.txt"):
      file_reader = read_fastq_file
    elif len(filename) == 2:
      file_reader = read_seq_prb_file
    else:
      print "Unexpected content of file list."
      sys.exit()

    print "Reading",filename
    for name,seqorg,qualorg in file_reader(filename):
      name = ":".join(name)
      if tend == None:
        tend = len(seqorg)
        srange1 = str(tstart)+":"+str(tend)
      if start2ndread == None: start2ndread=max(len(seqorg),tstart2)
      seq=seqorg[tstart:tend]
      if (seq.count("N") <= options.numberN):
        write_out_soap_fa(outfile,options.expID+":"+name+":"+srange1,seq)

      if second_in_first:
        seq = seqorg[tstart2:tend2]
        if (seq.count("N") <= options.numberN):
          write_out_soap_fa(outfile_r2,options.expID+":"+name+":"+srange2,seq)

  if start2ndread == None: start2ndread = tend
  for filename in second_read:
    if len(filename) != 2 and filename.endswith("qseq.txt"):
      file_reader = read_qseq_file
    elif len(filename) != 2 and filename.endswith("fastq.txt"):
      file_reader = read_fastq_file
    elif len(filename) == 2:
      file_reader = read_seq_prb_file
    else:
      print "Unexpected content of file list."
      sys.exit()

    print "Reading",filename
    for name,seqorg,qualorg in file_reader(filename):
      name = ":".join(name)
      seq=seqorg[tstart2-start2ndread:tend2-start2ndread]
      if (seq.count("N") <= options.numberN):
        write_out_soap_fa(outfile_r2,options.expID+":"+name+":"+srange2,seq)

outfile.close()
if reads == 2: outfile_r2.close()

if not had_training_sequences:
  print "Did not read a single input file. Check path to Bustard folder:", options.path
  sys.exit()

seed_length = max(6,min(12,(min(tend-tstart,max_length_soap)-3)//2))
seed_length2 = seed_length
if reads == 2:
  seed_length2 = max(6,min(12,(min(tend2-tstart2,max_length_soap)-3)//2))

print ""
print "Calling SOAP..."
outfilename2 = options.tmp+"/"+timestamp+"_soap_output.txt"
cmdline = options.soap+" -s "+str(seed_length)+" -d "+options.reference+" -a "+outfilename+" -v "+str(options.mismatch)+" -f "+str(options.numberN)+" -g 0 -c 0 -w 1 -r 1 -p "+str(options.cores)+" -o "+outfilename2
print cmdline
proc = subprocess.Popen(cmdline,shell=True)
proc.wait()

if reads == 2:
  outfilename2_r2 = options.tmp+"/"+timestamp+"_soap_output_2.txt"
  cmdline = options.soap+" -s "+str(seed_length2)+" -d "+options.reference+" -a "+outfilename_r2+" -v "+str(options.mismatch)+" -f "+str(options.numberN)+" -g 0 -c 0 -w 1 -r 1 -p "+str(options.cores)+" -o "+outfilename2_r2
  print cmdline
  proc = subprocess.Popen(cmdline,shell=True)
  proc.wait()

if not options.keep:
  print ""
  print "Removing temporary SOAP input file:",outfilename
  proc = subprocess.Popen("rm -f "+outfilename,shell=True)
  proc.wait()
  if reads == 2:
    print "Removing temporary SOAP input file:",outfilename_r2
    proc = subprocess.Popen("rm -f "+outfilename_r2,shell=True)
    proc.wait()

print ""
print "Reading reference to memory..."
seq_dict = {}
for title,seq in read_fasta(options.reference):
  seq_dict[title.split()[0]]=seq

print ""
delta_bases = tend-tstart
print "Will extract",delta_bases,"bases from reference for mapped reads."
if (max_frags_created > 1) and (options.cores > 1):
   print "Sorting SOAP output by sequence ID"
   proc = subprocess.Popen("sort "+outfilename2+" > "+outfilename2+"_sort",shell=True)
   proc.wait()
   proc = subprocess.Popen("mv "+outfilename2+"_sort "+outfilename2,shell=True)
   proc.wait()
print "Iterating over SOAP output file"
count = eval_soap_output(outfilename2,options.outfile,seq_dict,delta_bases,options)
if not options.keep:
  print "Removing temporary SOAP output file",outfilename2
  proc = subprocess.Popen("rm -f "+outfilename2,shell=True)
print ""
print count,"training sequences available in",options.outfile

if reads == 2:
  print ""
  delta_bases = tend2-tstart2
  print "Will extract",delta_bases,"bases from reference for mapped reads of second read."
  if (max_frags_created > 1) and (options.cores > 1):
    print "Sorting SOAP output by sequence ID for second read"
    proc = subprocess.Popen("sort "+outfilename2_r2+" > "+outfilename2_r2+"_sort",shell=True)
    proc.wait()
    proc = subprocess.Popen("mv "+outfilename2_r2+"_sort "+outfilename2_r2,shell=True)
    proc.wait()
  print "Iterating over SOAP output file"
  count = eval_soap_output(outfilename2_r2,options.outfile+"_r2",seq_dict,delta_bases,options)
  if not options.keep:
    print "Removing temporary SOAP output file",outfilename2_r2
    proc = subprocess.Popen("rm -f "+outfilename2_r2,shell=True)
  print ""
  print count,"training sequences available in",options.outfile+"_r2"
