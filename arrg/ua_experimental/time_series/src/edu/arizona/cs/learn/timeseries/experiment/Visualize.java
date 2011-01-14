package edu.arizona.cs.learn.timeseries.experiment;

import java.io.File;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

import edu.arizona.cs.learn.algorithm.heatmap.HeatmapImage;
import edu.arizona.cs.learn.algorithm.render.Paint;
import edu.arizona.cs.learn.timeseries.model.Interval;
import edu.arizona.cs.learn.timeseries.model.SequenceType;
import edu.arizona.cs.learn.timeseries.model.Signature;
import edu.arizona.cs.learn.timeseries.model.symbols.Symbol;
import edu.arizona.cs.learn.util.RandomFile;
import edu.arizona.cs.learn.util.Utils;

public class Visualize {

	
	public static void main(String[] args) { 
		List<Interval> set1 = new ArrayList<Interval>();
		set1.add(Interval.make("A", 0, 8));
		set1.add(Interval.make("B", 4, 10));
		set1.add(Interval.make("C", 8, 15));
		set1.add(Interval.make("D", 2, 8));

		Paint.render(set1, "/Users/wkerr/Desktop/example1.png");
		System.out.println(SequenceType.allen.getSequence(set1));
		
		List<Interval> set2 = new ArrayList<Interval>();
		set2.add(Interval.make("C", 1, 3));
		set2.add(Interval.make("A", 3, 6));
		set2.add(Interval.make("B", 4, 9));
		set2.add(Interval.make("C", 6, 10));
		System.out.println(SequenceType.allen.getSequence(set2));
		set2.add(Interval.make("D", 0, 0));
		Paint.render(set2, "/Users/wkerr/Desktop/example2.png");

		List<Interval> set3 = new ArrayList<Interval>();
		set3.add(Interval.make("A", 1, 5));
		set3.add(Interval.make("B", 4, 6));
		set3.add(Interval.make("C", 5, 7));
		System.out.println(SequenceType.allen.getSequence(set3));
		set3.add(Interval.make("D", 0, 0));
		Paint.render(set3, "/Users/wkerr/Desktop/example3.png");
		
		
//		Paint.sample2();
//		niallData();
	}
	
	public static void niallData() { 
		String pid = RandomFile.getPID();
		String dir = "/tmp/niall-" + pid + "/";

		SyntheticClassification.generateClass(pid, "f", 0, 0, 25);
		SyntheticClassification.generateClass(pid, "g", 1.0, 0, 25);

		makeImages(dir, dir, "niall-f");
		makeImages(dir, dir, "niall-g");
	}
	
	public static void makeImages(String dataDir, String outputDir, String prefix) { 
		Map<Integer,List<Interval>> map = Utils.load(new File(dataDir + prefix + ".lisp"));
		Map<Integer,List<Symbol>> instances = new TreeMap<Integer,List<Symbol>>();
		for (Integer key : map.keySet())  
			instances.put(key, SequenceType.allen.getSequence(map.get(key)));

		System.out.println("Making images...");
		// build a signature....
		List<Integer> eIds = new ArrayList<Integer>(map.keySet());
		Signature s = new Signature(prefix);
		for (int i = 1; i <= 20; ++i) { 
			System.out.println("\t...i = " + i);
			s.update(instances.get(eIds.get(i-1)));
			
			if (i % 10 == 0)
				s = s.prune(3);
		}
		System.out.println("\t...signature trained");
		
		// print all of the regular images 
		for (int id : eIds) { 
			String pre = outputDir + prefix + "-" + id;
			
			Paint.render(map.get(id), pre + ".png");
			HeatmapImage.makeHeatmap(pre + "-hm.png", s.signature(), 0, map.get(id), SequenceType.allen);
		}
	}
}
