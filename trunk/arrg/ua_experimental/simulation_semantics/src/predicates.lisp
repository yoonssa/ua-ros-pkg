(in-package :simulation_semantics)

;;=================================================================
;; Predicate-related methods of world-state class

(defmethod annotate-with-predicates ((ws world-state))
  (let* ((predicates (loop for obj1-state in (objects-of ws)
                        append (compute-my-predicates obj1-state))))
                        ;collect (loop for obj2 in objects 
                        ;           unless (eq obj1 obj2) ;; Don't compute binary predicates with yourself
                        ;           do (compute-binary-predictes obj1 obj2 ws)))))
    (setf (predicates-of ws) predicates)))

(defmethod print-predicates ((ws world-state))
  (format t "Predicates of ~a at time ~d:~%" (first (space-instances-of ws)) (time-of ws))
  (loop for pred in (predicates-of ws)
     do (format t "~t~a~%" pred)))

;;=================================================================

#+ignore(defun compute-predicates (objects)
  "Generate all pairs of objects x and y, and compute 
   the predicates p(x,y) for each of them"
  (let* ((prm (make-permutator objects objects)))
    (loop for x = (funcall prm)
       until (null x)
       unless (eq (first x) (second x))
       do (print x))))
         
;; This sort of needs access to the simulator too, huh? - goals, etc.
(defmethod compute-my-predicates ((my-state object-state))
  (loop with me = (first (object-of my-state))
     for pred in (self-predicates-of me) 
     collect (list pred (gazebo-name-of me) (funcall pred my-state))))
   
(defun print-last-predicates (sim)
  (loop for state in (get-states-from-last-run sim)
     do (print-predicates state)))

;;==================================================================

(defun plot-predicates (sims pred obj)
  (call-service "plot" 'plotter-srv:Plot
                :plots (loop for sim in sims collect 
                            (loop with states = (get-states-from-last-run sim)
                               with start-time = (time-of (first states))
                               with x = (make-array (length states) :adjustable t :fill-pointer 0)
                               with y = (make-array (length states) :adjustable t :fill-pointer 0)
                               for state in states
                               for predicates = (predicates-of state)
                               do (loop for p in predicates 
                                     for obj = (second p)
                                     when (and (eq (first p) pred) (eq (second p) obj))
                                     do (vector-push-extend (- (time-of state) start-time) x)
                                       (vector-push-extend (first (last p)) y))
                               finally (return (make-msg "plotter/PlotData"
                                                         (name) (format nil "Predicate (~a ~a) of ~a simulator"
                                                                        pred obj sim)
                                                         (x_label) "time"
                                                         (y_label) (format nil "(~a ~a)"
                                                                           pred obj)
                                                         (x_data) x
                                                         (y_data) y))))))

;;==================================================================
;; Predicates

(defun force-mag (os)
  (sqrt (sum-of-squares (as-list (linear-of (force-of os))))))
       
(defun vel-mag (os)
  (sqrt (sum-of-squares (as-list (linear-of (velocity-of os))))))

(defun x-pos (os)
  (x-of (position-of (pose-of os))))

;; Hardcoded point for now
(defun dist-to-goal (os)
  (distance (position-of (pose-of os)) (make-instance 'xyz :x 4 :y 0 :z 0)))
                          
;;==================================================================

(defun sum-of-squares (numbers)
  (loop for x in numbers summing (expt x 2)))

(defmethod distance ((self physical-object) (other physical-object))
  (distance (position-of (pose-of self)) (position-of (pose-of other))))